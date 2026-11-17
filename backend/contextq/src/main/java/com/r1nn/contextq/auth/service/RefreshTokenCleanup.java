package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.repository.RefreshTokenRepository;
import com.r1nn.contextq.auth.repository.TokenFamilyRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Daily physical delete of refresh tokens and families one day past the family expiry (policy §2.1
 * "USED·REVOKED 토큰 레코드", db-design §3.3 TTL). Kept until then so reuse is still recognized as
 * reuse, not as an unknown token.
 */
@Component
public class RefreshTokenCleanup {

  static final Duration RETENTION_AFTER_EXPIRY = Duration.ofDays(1);
  private static final Logger log = LoggerFactory.getLogger(RefreshTokenCleanup.class);

  private final RefreshTokenRepository tokens;
  private final TokenFamilyRepository families;
  private final Clock clock;

  public RefreshTokenCleanup(
      RefreshTokenRepository tokens, TokenFamilyRepository families, Clock clock) {
    this.tokens = tokens;
    this.families = families;
    this.clock = clock;
  }

  /** 03:30 KST, after the 03:00 backup (policy §2.1). */
  @Scheduled(cron = "0 30 3 * * *", zone = "Asia/Seoul")
  @Transactional
  public void cleanup() {
    Instant threshold = clock.instant().minus(RETENTION_AFTER_EXPIRY);
    int deletedTokens = tokens.deleteOfFamiliesExpiredBefore(threshold);
    int deletedFamilies = families.deleteExpiredBefore(threshold);
    log.info("refresh_cleanup tokens={} families={}", deletedTokens, deletedFamilies);
  }
}
