package com.r1nn.contextq.chat.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
class ChatRepositoryTest {

  static final String SHA = "0123456789abcdef0123456789abcdef01234567";

  @Autowired private ConversationRepository conversations;
  @Autowired private MessageRepository messages;
  @Autowired private MessageSourceRepository sources;
  @Autowired private TransactionTemplate tx;
  @Autowired private JdbcTemplate jdbc;

  @Test
  void storesSnapshotAndSourcesAsValues() {
    long userId = newUser();
    Long answerId =
        tx.execute(
            s -> {
              Conversation c =
                  conversations.save(
                      Conversation.single(userId, "질문", "langchain_v03", Instant.now()));
              c.appendMessages(2);
              messages.save(Message.question(c, userId, "질문", 1));
              Message answer = messages.save(Message.pendingAnswer(c, userId, "req-1"));
              answer.applyMeta(
                  new AnswerSnapshot(
                      7L, SHA, LocalDate.of(2026, 10, 5), new BigDecimal("0.8732"), null),
                  false);
              sources.save(
                  MessageSource.of(
                      answer,
                      "langchain_v03",
                      "1",
                      "Agents > Basic",
                      "https://github.com/x/blob/" + SHA + "/a.md?plain=1#L1-L2",
                      null,
                      new BigDecimal("0.8732")));
              answer.finish(
                  MessageStatus.COMPLETED,
                  new AnswerOutcome(
                      "답변 [1] [3]",
                      null,
                      "stop",
                      "gpt-4o-mini-2024-07-18",
                      "single_v2",
                      1240,
                      312,
                      "[3]",
                      null,
                      80,
                      120,
                      1850,
                      5300));
              c.recordAnswerEnded(MessageStatus.COMPLETED, Instant.now());
              return answer.getId();
            });

    Message stored = messages.findById(answerId).orElseThrow();
    assertThat(stored.getStatus()).isEqualTo(MessageStatus.COMPLETED);
    assertThat(stored.getCommitSha()).isEqualTo(SHA);
    assertThat(stored.getModel()).isEqualTo("gpt-4o-mini-2024-07-18");
    assertThat(stored.getInvalidCitations()).isEqualTo("[3]");
    assertThat(stored.getTop1Similarity()).isEqualByComparingTo("0.8732");
    List<MessageSource> stored1 = sources.findByMessage_IdOrderByIdAsc(answerId);
    assertThat(stored1).singleElement().satisfies(s -> assertThat(s.getChunkId()).isNull());
    assertThat(
            jdbc.queryForObject(
                "SELECT jsonb_typeof(invalid_citations) FROM messages WHERE id = ?",
                String.class,
                answerId))
        .isEqualTo("array");
  }

  /** INV-11: two transactions on one conversation are serialized by the row lock. */
  @Test
  void conversationLockSerializesInProgressCheck() throws Exception {
    long userId = newUser();
    Long conversationId =
        tx.execute(
            s ->
                conversations
                    .save(Conversation.single(userId, "q", "langchain_v03", Instant.now()))
                    .getId());
    CountDownLatch firstLocked = new CountDownLatch(1);

    CompletableFuture<Long> first =
        CompletableFuture.supplyAsync(
            () ->
                tx.execute(
                    s -> {
                      Conversation c =
                          conversations.findByIdForUpdate(conversationId).orElseThrow();
                      long seen = messages.countInProgress(conversationId);
                      messages.save(Message.pendingAnswer(c, userId, "req-a"));
                      messages.flush();
                      firstLocked.countDown();
                      sleep(700); // hold the lock while the second request arrives
                      return seen;
                    }));
    assertThat(firstLocked.await(10, TimeUnit.SECONDS)).isTrue();
    long secondStarted = System.nanoTime();
    CompletableFuture<Long> second =
        CompletableFuture.supplyAsync(
            () ->
                tx.execute(
                    s -> {
                      conversations.findByIdForUpdate(conversationId).orElseThrow();
                      return messages.countInProgress(conversationId);
                    }));

    assertThat(first.get(10, TimeUnit.SECONDS)).isZero();
    assertThat(second.get(10, TimeUnit.SECONDS)).isEqualTo(1);
    long waitedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - secondStarted);
    assertThat(waitedMs).as("second request waited for the first commit").isGreaterThan(300);
  }

  private long newUser() {
    return jdbc.queryForObject(
        "INSERT INTO users (email, password_hash, role, status, login_failed_count, created_at,"
            + " updated_at) VALUES (?, 'hash', 'ROLE_USER', 'ACTIVE', 0, now(), now())"
            + " RETURNING id",
        Long.class,
        "repo-" + System.nanoTime() + "@example.com");
  }

  private static void sleep(long millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(e);
    }
  }
}
