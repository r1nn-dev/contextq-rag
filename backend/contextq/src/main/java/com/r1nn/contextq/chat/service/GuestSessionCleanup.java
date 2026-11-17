package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import java.time.Clock;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Daily delete of guest sessions 24 h past their expiry (policy §2.1 게스트 세션 레코드). Kept until then
 * for the per-IP new-session count. Usage logs stay (no FK, db-design §3.5).
 */
@Component
public class GuestSessionCleanup {

  static final Duration RETENTION_AFTER_EXPIRY = Duration.ofHours(24);
  private static final Logger log = LoggerFactory.getLogger(GuestSessionCleanup.class);

  private final GuestSessionRepository sessions;
  private final Clock clock;

  public GuestSessionCleanup(GuestSessionRepository sessions, Clock clock) {
    this.sessions = sessions;
    this.clock = clock;
  }

  @Scheduled(cron = "0 40 3 * * *", zone = "Asia/Seoul")
  @Transactional
  public int cleanup() {
    int deleted = sessions.deleteExpiredBefore(clock.instant().minus(RETENTION_AFTER_EXPIRY));
    log.info("guest_session_cleanup deleted={}", deleted);
    return deleted;
  }
}
