package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.service.ChatMessageService.AcceptCommand;
import com.r1nn.contextq.chat.service.ChatMessageService.Accepted;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.support.ChatStreamTestSupport;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

/** policy §8.1: 100 questions per KST day per user, counted from quota_cost. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class DailyQuotaTest {

  static final ZoneId KST = ZoneId.of("Asia/Seoul");

  @Autowired private ChatMessageService service;
  @Autowired private JdbcTemplate jdbc;

  @Test
  void hundredAndFirstQuestionOfTheDayIsRejected() {
    long userId = ChatStreamTestSupport.newUser(jdbc);
    long conversationId = seedQuestions(userId, 100, Instant.now());

    Throwable thrown = catchThrowable(() -> service.accept(command(userId)));

    assertThat(thrown).isInstanceOf(BusinessException.class);
    assertThat(((BusinessException) thrown).getErrorCode())
        .isEqualTo(ErrorCode.DAILY_QUOTA_EXCEEDED);
    assertThat(conversationId).isPositive();
  }

  @Test
  void questionsBeforeKstMidnightDoNotCount() {
    long userId = ChatStreamTestSupport.newUser(jdbc);
    Instant justBeforeMidnight = LocalDate.now(KST).atStartOfDay(KST).toInstant().minusSeconds(60);
    seedQuestions(userId, 100, justBeforeMidnight);

    assertThatCode(() -> service.accept(command(userId))).doesNotThrowAnyException();
  }

  @Test
  void concurrentQuestionsAtTheLimitAcceptOnlyOne() {
    long userId = ChatStreamTestSupport.newUser(jdbc);
    seedQuestions(userId, 99, Instant.now());

    List<CompletableFuture<Object>> calls =
        List.of(attempt(userId), attempt(userId), attempt(userId));

    List<Object> results = calls.stream().map(CompletableFuture::join).toList();
    assertThat(results).filteredOn(r -> r instanceof Accepted).hasSize(1);
    assertThat(results).filteredOn(r -> r == ErrorCode.DAILY_QUOTA_EXCEEDED).hasSize(2);
  }

  private CompletableFuture<Object> attempt(long userId) {
    return CompletableFuture.supplyAsync(
        () -> {
          try {
            return service.accept(command(userId));
          } catch (BusinessException e) {
            return e.getErrorCode();
          }
        });
  }

  /** Inserts {@code count} USER questions (cost 1) at {@code at}; returns the conversation ID. */
  private long seedQuestions(long userId, int count, Instant at) {
    Long conversationId =
        jdbc.queryForObject(
            "INSERT INTO conversations (user_id, title, mode, source_key, message_count,"
                + " created_at, updated_at) VALUES (?, 'seed', 'SINGLE', 'langchain_v03', 0,"
                + " ?, ?) RETURNING id",
            Long.class,
            userId,
            Timestamp.from(at),
            Timestamp.from(at));
    for (int i = 0; i < count; i++) {
      jdbc.update(
          "INSERT INTO messages (conversation_id, user_id, role, content, quota_cost, created_at,"
              + " updated_at) VALUES (?, ?, 'USER', 'q', 1, ?, ?)",
          conversationId,
          userId,
          Timestamp.from(at),
          Timestamp.from(at));
    }
    return conversationId;
  }

  private static AcceptCommand command(long userId) {
    return AcceptCommand.single(userId, null, "q", "langchain_v03", "req-quota");
  }
}
