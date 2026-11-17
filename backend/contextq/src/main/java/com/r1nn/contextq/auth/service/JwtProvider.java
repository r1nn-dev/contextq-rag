package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.JwtProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/**
 * Access Token issue and verification (api-spec 부록 D.1, policy §1.2).
 *
 * <p>HS256 with {@code JWT_SECRET}; claims {@code sub} (user ID), {@code role}, {@code iat}, {@code
 * exp}, {@code jti}. Stateless: a logout or role change takes effect only when the token expires (≤
 * 30 min, documented trade-off).
 */
@Component
public class JwtProvider {

  static final String ROLE_CLAIM = "role";
  static final int MIN_SECRET_BYTES = 32;

  private final SecretKey key;
  private final JwtProperties properties;
  private final Clock clock;
  private final JwtParser parser;

  public JwtProvider(JwtProperties properties, Clock clock) {
    byte[] secret =
        properties.secret() == null
            ? new byte[0]
            : properties.secret().getBytes(StandardCharsets.UTF_8);
    if (secret.length < MIN_SECRET_BYTES) {
      throw new IllegalStateException("JWT_SECRET must be at least 32 bytes");
    }
    this.key = Keys.hmacShaKeyFor(secret);
    this.properties = properties;
    this.clock = clock;
    this.parser =
        Jwts.parser()
            .verifyWith(key)
            .clockSkewSeconds(properties.clockSkew().toSeconds())
            .clock(() -> Date.from(clock.instant()))
            .build();
  }

  /** Verified token content. */
  public record AccessClaims(Long userId, UserRole role, String tokenId) {}

  public String issue(Long userId, UserRole role) {
    Instant now = clock.instant();
    return Jwts.builder()
        .subject(String.valueOf(userId))
        .claim(ROLE_CLAIM, role.name())
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plus(properties.accessTokenTtl())))
        .id(UUID.randomUUID().toString())
        .signWith(key, Jwts.SIG.HS256)
        .compact();
  }

  /** Lifetime in seconds for the {@code expiresIn} response field. */
  public long expiresInSeconds() {
    return properties.accessTokenTtl().toSeconds();
  }

  /**
   * @throws BusinessException {@code AUTH_TOKEN_EXPIRED} past {@code exp} + 30 s; {@code
   *     AUTH_TOKEN_INVALID} for a bad signature, malformed token or unknown claims
   */
  public AccessClaims verify(String token) {
    try {
      Claims claims = parser.parseSignedClaims(token).getPayload();
      return new AccessClaims(
          Long.valueOf(claims.getSubject()),
          UserRole.valueOf(claims.get(ROLE_CLAIM, String.class)),
          claims.getId());
    } catch (ExpiredJwtException e) {
      throw new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED);
    } catch (JwtException | IllegalArgumentException | NullPointerException e) {
      throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
    }
  }
}
