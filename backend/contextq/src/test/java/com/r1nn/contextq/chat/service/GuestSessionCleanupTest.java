package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.GuestSession;
import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** policy §2.1: guest session rows are deleted 24 h after they expire. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class GuestSessionCleanupTest {

  @Autowired private GuestSessionCleanup cleanup;
  @Autowired private GuestSessionRepository sessions;

  @Test
  void deletesOnlySessionsExpiredMoreThanADayAgo() {
    Instant now = Instant.now();
    GuestSession old = save(now.minus(Duration.ofHours(49))); // expired 25 h ago
    GuestSession recent = save(now.minus(Duration.ofHours(47))); // expired 23 h ago

    cleanup.cleanup();

    assertThat(sessions.findById(old.getId())).isEmpty();
    assertThat(sessions.findById(recent.getId())).isPresent();
  }

  private GuestSession save(Instant issuedAt) {
    return sessions.saveAndFlush(
        GuestSession.open(String.format("%064x", System.nanoTime()), "192.0.2.9", issuedAt));
  }
}
