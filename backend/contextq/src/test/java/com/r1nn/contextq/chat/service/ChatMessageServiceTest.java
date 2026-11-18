package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.QuestionTarget;
import com.r1nn.contextq.chat.domain.RewriteStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.chat.service.ChatMessageService.AcceptCommand;
import com.r1nn.contextq.chat.service.ChatMessageService.Accepted;
import com.r1nn.contextq.chat.service.ChatMessageService.SourceValue;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
class ChatMessageServiceTest {

  static final String SHA = "0123456789abcdef0123456789abcdef01234567";

  @Autowired private ChatMessageService service;
  @Autowired private ConversationRepository conversations;
  @Autowired private MessageRepository messages;
  @Autowired private MessageSourceRepository sources;
  @Autowired private JdbcTemplate jdbc;

  private long userId;

  @BeforeEach
  void setUp() {
    userId = newUser();
  }

  @Test
  void acceptCreatesConversationQuestionAndPendingAnswer() {
    Accepted accepted = service.accept(newQuestion("Agent 생성 방법"));

    assertThat(conversations.findById(accepted.conversationId()))
        .hasValueSatisfying(
            c -> {
              assertThat(c.getMessageCount()).isEqualTo(2);
              assertThat(c.getTitle()).isEqualTo("Agent 생성 방법");
            });
    Message answer = messages.findById(accepted.answerId()).orElseThrow();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.PENDING);
    assertThat(answer.getRequestId()).isEqualTo("req-1");
    assertThat(messages.findById(accepted.questionId()).orElseThrow().getQuotaCost())
        .isEqualTo((short) 1);
  }

  @Test
  void streamLifecycleStoresSnapshotSourcesAndTerminalValues() {
    Accepted accepted = service.accept(newQuestion("q"));

    service.applyMeta(
        accepted.answerId(),
        "langchain_v03",
        new AnswerSnapshot(7L, SHA, LocalDate.of(2026, 10, 5), new BigDecimal("0.8732"), null),
        false,
        List.of(
            new SourceValue(
                "1",
                "Agents > Basic",
                "https://github.com/x/blob/" + SHA + "/a.md",
                null,
                new BigDecimal("0.8732"))));
    MessageStatus stored =
        service.finish(
            accepted.answerId(),
            MessageStatus.COMPLETED,
            new AnswerOutcome(
                "답변 [1]", null, "stop", "gpt-4o-mini", "single_v2", 10, 5, "[]", null, 1, 2, 3, 4));

    assertThat(stored).isEqualTo(MessageStatus.COMPLETED);
    Message answer = messages.findById(accepted.answerId()).orElseThrow();
    assertThat(answer.getContent()).isEqualTo("답변 [1]");
    assertThat(answer.getIngestRunId()).isEqualTo(7L);
    assertThat(sources.findByMessage_IdOrderByIdAsc(accepted.answerId())).hasSize(1);
    assertThat(
            conversations.findById(accepted.conversationId()).orElseThrow().getLastMessageStatus())
        .isEqualTo(MessageStatus.COMPLETED);
  }

  @Test
  void secondTerminalUpdateIsIgnored() {
    Accepted accepted = service.accept(newQuestion("q"));
    service.finish(
        accepted.answerId(), MessageStatus.FAILED, AnswerOutcome.interrupted("", "STALE"));

    MessageStatus stored =
        service.finish(
            accepted.answerId(), MessageStatus.FAILED, AnswerOutcome.interrupted("", "AI_BUSY"));

    assertThat(stored).isEqualTo(MessageStatus.FAILED);
    assertThat(messages.findById(accepted.answerId()).orElseThrow().getStatusReason())
        .isEqualTo("STALE");
  }

  @Test
  void unreachableTerminalIsStoredAsFailed() {
    Accepted accepted = service.accept(newQuestion("q"));

    MessageStatus stored =
        service.finish(
            accepted.answerId(), MessageStatus.PARTIAL, AnswerOutcome.interrupted("", "LLM_ERROR"));

    assertThat(stored).isEqualTo(MessageStatus.FAILED);
  }

  @Test
  void followUpToBusyConversationIsRejected() {
    Accepted first = service.accept(newQuestion("q"));

    assertCode(
        () -> service.accept(followUp(first.conversationId(), null)), ErrorCode.CONVERSATION_BUSY);
  }

  @Test
  void followUpAfterTerminalAnswerIsAccepted() {
    Accepted first = service.accept(newQuestion("q"));
    service.finish(first.answerId(), MessageStatus.FAILED, AnswerOutcome.interrupted("", "X"));

    Accepted second = service.accept(followUp(first.conversationId(), "langchain_v03"));

    assertThat(second.conversationId()).isEqualTo(first.conversationId());
    assertThat(conversations.findById(first.conversationId()).orElseThrow().getMessageCount())
        .isEqualTo(4);
  }

  @Test
  void foreignConversationIsNotFound() {
    Accepted mine = service.accept(newQuestion("q"));
    long otherUser = newUser();

    assertCode(
        () ->
            service.accept(
                AcceptCommand.single(otherUser, mine.conversationId(), "q", null, "req-2")),
        ErrorCode.CONVERSATION_NOT_FOUND);
    assertCode(
        () ->
            service.conversationTarget(
                otherUser, mine.conversationId(), QuestionTarget.single(null)),
        ErrorCode.CONVERSATION_NOT_FOUND);
    assertCode(
        () -> service.conversationTarget(userId, 999_999L, QuestionTarget.single(null)),
        ErrorCode.CONVERSATION_NOT_FOUND);
  }

  @Test
  void differentVersionOnFollowUpIsInvalid() {
    Accepted first = service.accept(newQuestion("q"));

    assertThatThrownBy(
            () ->
                service.conversationTarget(
                    userId, first.conversationId(), QuestionTarget.single("langchain_v1x")))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.getErrorCode()).isEqualTo(ErrorCode.INVALID_REQUEST);
              assertThat(e.getDetails().getFirst().field()).isEqualTo("sourceKey");
            });
  }

  @Test
  void fullConversationIsRejected() {
    Accepted first = service.accept(newQuestion("q"));
    service.finish(first.answerId(), MessageStatus.FAILED, AnswerOutcome.interrupted("", "X"));
    jdbc.update(
        "UPDATE conversations SET message_count = 100 WHERE id = ?", first.conversationId());

    assertCode(
        () -> service.accept(followUp(first.conversationId(), null)), ErrorCode.CONVERSATION_FULL);
  }

  @Test
  void newConversationHasNoHistoryAndSkipsTheRewrite() {
    Accepted first = service.accept(newQuestion("q"));

    assertThat(first.history()).isEmpty();
    assertThat(messages.findById(first.answerId()).orElseThrow().getRewriteStatus())
        .isEqualTo(RewriteStatus.SKIPPED);
  }

  @Test
  void followUpHistoryIsTheLastThreeTurnsWithoutFailedOrNoContextAnswers() {
    Accepted t1 = service.accept(newQuestion("질문1"));
    answer(t1, MessageStatus.COMPLETED, "답1");
    Accepted t2 = service.accept(followUpWith(t1.conversationId(), "질문2"));
    service.finish(t2.answerId(), MessageStatus.FAILED, AnswerOutcome.interrupted("", "X"));
    Accepted t3 = service.accept(followUpWith(t1.conversationId(), "질문3"));
    service.applyMeta(t3.answerId(), "langchain_v03", snapshot(null), true, List.of());
    service.finish(t3.answerId(), MessageStatus.NO_CONTEXT, outcome("근거 부족 안내"));
    Accepted t4 = service.accept(followUpWith(t1.conversationId(), "질문4"));
    answer(t4, MessageStatus.PARTIAL, "가".repeat(2500));

    Accepted t5 = service.accept(followUpWith(t1.conversationId(), "질문5"));

    assertThat(t5.history())
        .extracting(m -> m.get("role") + ":" + m.get("content").substring(0, 3))
        .containsExactly("user:질문2", "user:질문3", "user:질문4", "assistant:가가가");
    assertThat(t5.history().getLast().get("content")).hasSize(2000);
    assertThat(messages.findById(t5.answerId()).orElseThrow().getRewriteStatus()).isNull();
  }

  @Test
  void rewriteStatusFollowsTheMetaWhenHistoryWasSent() {
    Accepted t1 = service.accept(newQuestion("질문1"));
    answer(t1, MessageStatus.COMPLETED, "답1");
    Accepted ok = service.accept(followUpWith(t1.conversationId(), "그건?"));
    service.applyMeta(ok.answerId(), "langchain_v03", snapshot("재작성 질의"), false, List.of());
    service.finish(ok.answerId(), MessageStatus.COMPLETED, outcome("답2"));
    Accepted fallback = service.accept(followUpWith(t1.conversationId(), "그럼?"));
    service.applyMeta(fallback.answerId(), "langchain_v03", snapshot(null), false, List.of());

    Message okAnswer = messages.findById(ok.answerId()).orElseThrow();
    assertThat(okAnswer.getRewriteStatus()).isEqualTo(RewriteStatus.OK);
    assertThat(okAnswer.getRewrittenQuery()).isEqualTo("재작성 질의");
    Message fallbackAnswer = messages.findById(fallback.answerId()).orElseThrow();
    assertThat(fallbackAnswer.getRewriteStatus()).isEqualTo(RewriteStatus.FALLBACK);
    assertThat(fallbackAnswer.getRewrittenQuery()).isNull();
  }

  private void answer(Accepted accepted, MessageStatus status, String content) {
    service.applyMeta(accepted.answerId(), "langchain_v03", snapshot(null), false, List.of());
    service.finish(accepted.answerId(), status, outcome(content));
  }

  private static AnswerSnapshot snapshot(String rewrittenQuery) {
    return new AnswerSnapshot(7L, SHA, LocalDate.of(2026, 10, 5), null, rewrittenQuery);
  }

  private static AnswerOutcome outcome(String content) {
    return new AnswerOutcome(
        content, null, "stop", "gpt-4o-mini", "single_v2", 10, 5, null, null, 1, 1, 1, 3);
  }

  private AcceptCommand followUpWith(Long conversationId, String question) {
    return AcceptCommand.single(userId, conversationId, question, null, "req-" + System.nanoTime());
  }

  private AcceptCommand newQuestion(String question) {
    return AcceptCommand.single(userId, null, question, "langchain_v03", "req-1");
  }

  private AcceptCommand followUp(Long conversationId, String sourceKey) {
    return AcceptCommand.single(userId, conversationId, "다음 질문", sourceKey, "req-2");
  }

  private static void assertCode(Runnable call, ErrorCode code) {
    assertThatThrownBy(call::run)
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.getErrorCode()).isEqualTo(code));
  }

  private long newUser() {
    return jdbc.queryForObject(
        "INSERT INTO users (email, password_hash, role, status, login_failed_count, created_at,"
            + " updated_at) VALUES (?, 'hash', 'ROLE_USER', 'ACTIVE', 0, now(), now())"
            + " RETURNING id",
        Long.class,
        "svc-" + System.nanoTime() + "@example.com");
  }
}
