package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.QuestionTarget;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.service.ChatMessageService.AcceptCommand;
import com.r1nn.contextq.chat.service.ChatMessageService.Accepted;
import com.r1nn.contextq.support.ChatStreamTestSupport;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

/** policy §2.1·§2.3, db-design §5: stuck STREAMING·PENDING end as FAILED(STALE / PERSIST_ERROR). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class StaleAnswerSweeperTest {

  @Autowired private StaleAnswerSweeper sweeper;
  @Autowired private ChatMessageService chatMessages;
  @Autowired private PersistFailureRegistry persistFailures;
  @Autowired private MessageRepository messages;
  @Autowired private ConversationRepository conversations;
  @Autowired private JdbcTemplate jdbc;

  @Test
  void endsStuckAnswersAndLeavesOthers() {
    long userId = ChatStreamTestSupport.newUser(jdbc);
    Accepted streaming = streaming(userId);
    Accepted pending = chatMessages.accept(command(userId));
    Accepted recent = streaming(userId);
    Accepted completed = streaming(userId);
    chatMessages.finish(
        completed.answerId(), MessageStatus.COMPLETED, AnswerOutcome.interrupted("ok", null));
    Accepted persistFailed = streaming(userId);
    persistFailures.record(persistFailed.answerId(), "브라우저가 받은 답변");
    age(List.of(streaming, pending, completed, persistFailed), 200);
    age(List.of(recent), 120);

    sweeper.sweep();

    assertEnded(streaming, "STALE");
    assertEnded(pending, "STALE");
    Message persisted = messages.findById(persistFailed.answerId()).orElseThrow();
    assertThat(persisted.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(persisted.getStatusReason()).isEqualTo("PERSIST_ERROR");
    assertThat(persisted.getContent()).isEqualTo("브라우저가 받은 답변");
    assertThat(status(recent)).isEqualTo(MessageStatus.STREAMING);
    assertThat(status(completed)).isEqualTo(MessageStatus.COMPLETED);
    assertThat(
            conversations.findById(streaming.conversationId()).orElseThrow().getLastMessageStatus())
        .isEqualTo(MessageStatus.FAILED);
  }

  @Test
  void endsCompareAnswersStuckInProcessing() {
    long userId = ChatStreamTestSupport.newUser(jdbc);
    Accepted processing =
        chatMessages.accept(
            new AcceptCommand(
                userId,
                null,
                "q",
                QuestionTarget.compare("langchain_v03", "langchain_v1x"),
                "req-sweep-compare"));
    chatMessages.startProcessing(processing.answerId());
    age(List.of(processing), 200);

    sweeper.sweep();

    assertEnded(processing, "STALE");
  }

  private Accepted streaming(long userId) {
    Accepted accepted = chatMessages.accept(command(userId));
    chatMessages.applyMeta(
        accepted.answerId(),
        "langchain_v03",
        new AnswerSnapshot(7L, ChatStreamTestSupport.SHA, LocalDate.of(2026, 10, 5), null, null),
        false,
        List.of());
    return accepted;
  }

  private void age(List<Accepted> answers, int seconds) {
    for (Accepted a : answers) {
      jdbc.update(
          "UPDATE messages SET updated_at = now() - make_interval(secs => ?) WHERE id = ?",
          seconds,
          a.answerId());
    }
  }

  private void assertEnded(Accepted accepted, String reason) {
    Message answer = messages.findById(accepted.answerId()).orElseThrow();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo(reason);
  }

  private MessageStatus status(Accepted accepted) {
    return messages.findById(accepted.answerId()).orElseThrow().getStatus();
  }

  private static AcceptCommand command(long userId) {
    return AcceptCommand.single(userId, null, "q", "langchain_v03", "req-sweep");
  }
}
