package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.RefreshToken;
import com.r1nn.contextq.auth.domain.TokenFamily;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.auth.repository.RefreshTokenRepository;
import com.r1nn.contextq.auth.repository.TokenFamilyRepository;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.JwtProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Refresh token families with rotation and reuse detection (api-spec §1.2~§1.4, policy §1.2·§10.3).
 *
 * <ul>
 *   <li>Login starts a family (absolute 7 days); at most 10 ACTIVE families per user, the oldest is
 *       revoked first.
 *   <li>Rotation marks the presented token USED and issues the next ACTIVE token in one transaction
 *       under the family row lock (INV-15).
 *   <li>A USED token sent again within 5 s is a multi-tab race (409); later it is theft — the whole
 *       family is revoked (401 {@code AUTH_REFRESH_REUSED}).
 * </ul>
 */
@Service
public class RefreshTokenService {

  static final int MAX_ACTIVE_FAMILIES = 10;
  private static final int TOKEN_BYTES = 32; // 256 bits
  private static final Logger log = LoggerFactory.getLogger(RefreshTokenService.class);

  private final TokenFamilyRepository families;
  private final RefreshTokenRepository tokens;
  private final UserRepository users;
  private final RefreshCookies cookies;
  private final JwtProperties properties;
  private final Clock clock;
  private final SecureRandom random = new SecureRandom();

  public RefreshTokenService(
      TokenFamilyRepository families,
      RefreshTokenRepository tokens,
      UserRepository users,
      RefreshCookies cookies,
      JwtProperties properties,
      Clock clock) {
    this.families = families;
    this.tokens = tokens;
    this.users = users;
    this.cookies = cookies;
    this.properties = properties;
    this.clock = clock;
  }

  /** New raw token (cookie value only) and the cookie lifetime. */
  public record Issued(String rawToken, Duration maxAge) {}

  /** Rotation result: who to issue the Access Token for, and the next refresh token. */
  public record Rotated(Long userId, UserRole role, Issued next) {}

  /** Login: new family + first token, after enforcing the 10-family cap. */
  @Transactional
  public Issued startFamily(Long userId) {
    Instant now = clock.instant();
    List<TokenFamily> active = families.findActive(userId, now);
    for (int i = 0; i <= active.size() - MAX_ACTIVE_FAMILIES; i++) {
      revokeFamily(active.get(i), now);
    }
    TokenFamily family =
        families.save(TokenFamily.start(userId, now, properties.refreshFamilyTtl()));
    return new Issued(issueToken(family, now), properties.refreshFamilyTtl());
  }

  /**
   * {@code POST /api/v1/auth/refresh}.
   *
   * @throws BusinessException MISSING · INVALID · EXPIRED · CONFLICT · REUSED (api-spec §1.3);
   *     INVALID·EXPIRED·REUSED carry a {@code Set-Cookie} header that deletes the cookie
   */
  @Transactional(noRollbackFor = BusinessException.class)
  public Rotated rotate(String rawToken) {
    if (rawToken == null || rawToken.isBlank()) {
      throw new BusinessException(ErrorCode.AUTH_REFRESH_MISSING);
    }
    String hash = hash(rawToken);
    Long familyId =
        tokens
            .findFamilyIdByTokenHash(hash)
            .orElseThrow(() -> clearing(ErrorCode.AUTH_REFRESH_INVALID));
    TokenFamily family =
        families
            .findByIdForUpdate(familyId)
            .orElseThrow(() -> clearing(ErrorCode.AUTH_REFRESH_INVALID));
    RefreshToken presented =
        tokens.findByTokenHash(hash).orElseThrow(() -> clearing(ErrorCode.AUTH_REFRESH_INVALID));
    Instant now = clock.instant();

    if (family.isRevoked() || presented.getStatus() == RefreshToken.Status.REVOKED) {
      throw clearing(ErrorCode.AUTH_REFRESH_INVALID);
    }
    if (family.isExpiredAt(now)) {
      throw clearing(ErrorCode.AUTH_REFRESH_EXPIRED);
    }
    if (presented.getStatus() == RefreshToken.Status.USED) {
      if (presented.usedWithin(properties.refreshReuseGrace(), now)) {
        throw new BusinessException(ErrorCode.AUTH_REFRESH_CONFLICT);
      }
      revokeFamily(family, now);
      log.warn("refresh_reuse_detected familyId={} userId={}", family.getId(), family.getUserId());
      throw clearing(ErrorCode.AUTH_REFRESH_REUSED);
    }

    presented.markUsed(now);
    String next = issueToken(family, now);
    User user =
        users
            .findById(family.getUserId())
            .orElseThrow(() -> clearing(ErrorCode.AUTH_REFRESH_INVALID));
    return new Rotated(user.getId(), user.getRole(), new Issued(next, family.remainingAt(now)));
  }

  /** {@code POST /api/v1/auth/logout}: revokes the family; unknown or missing cookie is fine. */
  @Transactional
  public void logout(String rawToken) {
    if (rawToken == null || rawToken.isBlank()) {
      return;
    }
    tokens
        .findFamilyIdByTokenHash(hash(rawToken))
        .flatMap(families::findByIdForUpdate)
        .ifPresent(family -> revokeFamily(family, clock.instant()));
  }

  private void revokeFamily(TokenFamily family, Instant now) {
    family.revoke();
    tokens.findByFamily_Id(family.getId()).forEach(token -> token.revoke(now));
  }

  private String issueToken(TokenFamily family, Instant now) {
    byte[] bytes = new byte[TOKEN_BYTES];
    random.nextBytes(bytes);
    String raw = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    tokens.save(RefreshToken.issue(family, hash(raw), now));
    return raw;
  }

  private BusinessException clearing(ErrorCode code) {
    return new BusinessException(
        code, code.defaultMessage(), List.of(), Map.of(HttpHeaders.SET_COOKIE, cookies.clear()));
  }

  /** SHA-256 hex (64 chars) — the only form stored in the database. */
  static String hash(String rawToken) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(rawToken.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }
}
