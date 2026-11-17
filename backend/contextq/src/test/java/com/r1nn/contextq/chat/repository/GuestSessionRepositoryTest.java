package com.r1nn.contextq.chat.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.GuestSession;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

/** INV-16: atomic deduction keeps used_count within 0..5 even under concurrency. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class GuestSessionRepositoryTest {

  @Autowired private GuestSessionRepository sessions;
  @Autowired private TransactionTemplate tx;
  @Autowired private JdbcTemplate jdbc;

  @Test
  void twentyConcurrentQuestionsChargeExactlyFive() {
    String hash = newSession(Instant.now());

    List<CompletableFuture<Integer>> calls =
        IntStream.range(0, 20)
            .mapToObj(i -> CompletableFuture.supplyAsync(() -> consume(hash)))
            .toList();

    int charged = calls.stream().mapToInt(CompletableFuture::join).sum();
    GuestSession session = sessions.findBySidHash(hash).orElseThrow();
    assertThat(charged).isEqualTo(5);
    assertThat(session.getUsedCount()).isEqualTo((short) 5);
    assertThat(session.getStatus()).isEqualTo(GuestSession.Status.EXHAUSTED);
  }

  @Test
  void expiredSessionIsNotCharged() {
    String hash = newSession(Instant.now().minus(Duration.ofHours(25)));

    assertThat(consume(hash)).isZero();
  }

  @Test
  void refundReopensExhaustedSessionOnce() {
    String hash = newSession(Instant.now());
    for (int i = 0; i < 5; i++) {
      consume(hash);
    }

    assertThat(refund(hash)).isEqualTo(1);

    GuestSession session = sessions.findBySidHash(hash).orElseThrow();
    assertThat(session.getUsedCount()).isEqualTo((short) 4);
    assertThat(session.getStatus()).isEqualTo(GuestSession.Status.ACTIVE);
  }

  @Test
  void refundNeverGoesBelowZero() {
    String hash = newSession(Instant.now());

    assertThat(refund(hash)).isZero();
  }

  @Test
  void checkConstraintRejectsSix() {
    String hash = newSession(Instant.now());

    assertThatThrownBy(
            () -> jdbc.update("UPDATE guest_sessions SET used_count = 6 WHERE sid_hash = ?", hash))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  private int consume(String hash) {
    Integer charged = tx.execute(s -> sessions.consume(hash, Instant.now()));
    return charged == null ? 0 : charged;
  }

  private int refund(String hash) {
    Integer refunded = tx.execute(s -> sessions.refund(hash, Instant.now()));
    return refunded == null ? 0 : refunded;
  }

  private String newSession(Instant issuedAt) {
    String hash = String.format("%064x", System.nanoTime());
    sessions.saveAndFlush(GuestSession.open(hash, "203.0.113.7", issuedAt));
    return hash;
  }
}
