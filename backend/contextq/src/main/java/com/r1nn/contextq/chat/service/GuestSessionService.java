package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.GuestSession;
import com.r1nn.contextq.chat.domain.GuestUsageLog;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import com.r1nn.contextq.chat.repository.GuestUsageLogRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.GuestProperties;
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
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Guest sessions and the 5-question limit (policy §1.3, api-spec §3.1·부록 D.3).
 *
 * <ul>
 *   <li>The cookie is issued on the first question only. A missing, unknown or expired cookie gets
 *       a new session (at most 30 per IP per hour); an exhausted but unexpired session does not —
 *       that would reset the limit.
 *   <li>Every question is charged by one conditional UPDATE (INV-16).
 *   <li>A server-side failure before {@code meta} refunds once.
 * </ul>
 */
@Service
public class GuestSessionService {

  private static final int SID_BYTES = 16; // 128 bits
  private static final int MAX_IP_LENGTH = 45;
  private static final Duration IP_WINDOW = Duration.ofHours(1);
  private static final Logger log = LoggerFactory.getLogger(GuestSessionService.class);

  private final GuestSessionRepository sessions;
  private final GuestUsageLogRepository usageLogs;
  private final GuestCookies cookies;
  private final GuestProperties properties;
  private final Clock clock;
  private final SecureRandom random = new SecureRandom();

  public GuestSessionService(
      GuestSessionRepository sessions,
      GuestUsageLogRepository usageLogs,
      GuestCookies cookies,
      GuestProperties properties,
      Clock clock) {
    this.sessions = sessions;
    this.usageLogs = usageLogs;
    this.cookies = cookies;
    this.properties = properties;
    this.clock = clock;
  }

  /**
   * One charged question.
   *
   * @param setCookie {@code Set-Cookie} value when a new session was issued, otherwise null
   */
  public record GuestTicket(String sidHash, String setCookie) {}

  /** {@code guest} object of the source list (api-spec §2.1). */
  public record GuestStatus(int limit, int used, int remaining, Instant expiresAt) {}

  /**
   * Finds or issues the session and charges one question.
   *
   * @throws BusinessException {@code GUEST_SESSION_LIMIT} or {@code GUEST_QUOTA_EXCEEDED}
   */
  @Transactional
  public GuestTicket charge(String rawSid, String ipAddress) {
    Instant now = clock.instant();
    Optional<GuestSession> current = find(rawSid).filter(s -> !s.isExpiredAt(now));
    String sidHash;
    String setCookie = null;
    if (current.isPresent()) {
      sidHash = current.get().getSidHash();
    } else {
      String ip = truncateIp(ipAddress);
      if (sessions.countByIpAddressAndCreatedAtAfter(ip, now.minus(IP_WINDOW))
          >= properties.sessionsPerIpPerHour()) {
        throw new BusinessException(ErrorCode.GUEST_SESSION_LIMIT);
      }
      String raw = newSid();
      sidHash = hash(raw);
      sessions.save(GuestSession.open(sidHash, ip, now));
      setCookie = cookies.issue(raw, GuestSession.LIFETIME);
    }
    if (sessions.consume(sidHash, now) == 0) {
      throw new BusinessException(ErrorCode.GUEST_QUOTA_EXCEEDED);
    }
    return new GuestTicket(sidHash, setCookie);
  }

  /** One refund after a server-side failure before {@code meta} (policy §1.3). */
  @Transactional
  public void refund(String sidHash) {
    if (sessions.refund(sidHash, clock.instant()) == 0) {
      log.warn("guest_refund_skipped — nothing charged");
    }
  }

  /** Usage log row for a finished guest answer (policy §6.3 step 5). */
  @Transactional
  public void record(
      String sidHash, MessageStatus status, Integer promptTokens, Integer completionTokens) {
    usageLogs.save(
        GuestUsageLog.of(sidHash, status, promptTokens, completionTokens, clock.instant()));
  }

  /** Current usage for the source list; never issues a cookie. */
  @Transactional(readOnly = true)
  public GuestStatus status(String rawSid) {
    Instant now = clock.instant();
    return find(rawSid)
        .filter(s -> !s.isExpiredAt(now))
        .map(
            s ->
                new GuestStatus(
                    GuestSession.LIMIT, s.getUsedCount(), s.remaining(), s.getExpiresAt()))
        .orElseGet(() -> new GuestStatus(GuestSession.LIMIT, 0, GuestSession.LIMIT, null));
  }

  /** {@code Set-Cookie} header map for errors that must still deliver a new cookie. */
  public static Map<String, String> cookieHeader(GuestTicket ticket) {
    return ticket.setCookie() == null
        ? Map.of()
        : Map.of(HttpHeaders.SET_COOKIE, ticket.setCookie());
  }

  /** Same error with the new session cookie attached (when one was issued). */
  public static BusinessException withCookie(BusinessException e, GuestTicket ticket) {
    if (ticket.setCookie() == null) {
      return e;
    }
    return new BusinessException(
        e.getErrorCode(), e.getMessage(), List.copyOf(e.getDetails()), cookieHeader(ticket));
  }

  private Optional<GuestSession> find(String rawSid) {
    if (rawSid == null || rawSid.isBlank() || rawSid.length() > 64) {
      return Optional.empty();
    }
    return sessions.findBySidHash(hash(rawSid));
  }

  private String newSid() {
    byte[] bytes = new byte[SID_BYTES];
    random.nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  private static String truncateIp(String ip) {
    if (ip == null || ip.isBlank()) {
      return "unknown";
    }
    return ip.length() <= MAX_IP_LENGTH ? ip : ip.substring(0, MAX_IP_LENGTH);
  }

  static String hash(String raw) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }
}
