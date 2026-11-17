package com.r1nn.contextq.chat.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

/** Entity rules without a database: INV-10 seal, INV-12 guard, title, message cap. */
class ConversationMessageTest {

  static final Instant NOW = Instant.parse("2026-11-18T00:00:00Z");

  @Test
  void titleIsFirst40CharsWithoutLineBreaks() {
    String question = "LangChain v0.3에서\nAgent를 어떻게 생성하나요? 그리고 Tool은 어떻게 등록하나요? 추가 질문";

    Conversation c = Conversation.single(1L, question, "langchain_v03", NOW);

    assertThat(c.getTitle()).hasSize(40).doesNotContain("\n").startsWith("LangChain v0.3에서 Agent");
  }

  @Test
  void modeAndSourceKeysHaveNoSetter() {
    boolean hasMutator =
        Arrays.stream(Conversation.class.getDeclaredMethods())
            .filter(m -> Modifier.isPublic(m.getModifiers()))
            .map(Method::getName)
            .anyMatch(n -> n.startsWith("set"));

    assertThat(hasMutator).as("INV-10: no public setter on Conversation").isFalse();
  }

  @Test
  void messageCapIsHundred() {
    Conversation c = Conversation.single(1L, "q", "langchain_v03", NOW);
    for (int i = 0; i < 49; i++) {
      c.appendMessages(2);
    }

    assertThat(c.canAppend(2)).isTrue();
    c.appendMessages(2);
    assertThat(c.getMessageCount()).isEqualTo(100);
    assertThat(c.canAppend(2)).isFalse();
    assertThatThrownBy(() -> c.appendMessages(2)).isInstanceOf(IllegalStateException.class);
  }

  @Test
  void answerEndUpdatesListFields() {
    Conversation c = Conversation.single(1L, "q", "langchain_v03", NOW);

    c.recordAnswerEnded(MessageStatus.COMPLETED, NOW.plusSeconds(5));

    assertThat(c.getLastMessageStatus()).isEqualTo(MessageStatus.COMPLETED);
    assertThat(c.getUpdatedAt()).isEqualTo(NOW.plusSeconds(5));
    assertThatThrownBy(() -> c.recordAnswerEnded(MessageStatus.STREAMING, NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void metaMovesPendingToStreamingAndCopiesSnapshot() {
    Message answer = pendingAnswer();

    answer.applyMeta(snapshot(), false);

    assertThat(answer.getStatus()).isEqualTo(MessageStatus.STREAMING);
    assertThat(answer.getIngestRunId()).isEqualTo(7L);
    assertThat(answer.getIngestedAt()).isEqualTo(LocalDate.of(2026, 10, 5));
  }

  @Test
  void noContextMetaKeepsPendingThenFinishesAsNoContext() {
    Message answer = pendingAnswer();

    answer.applyMeta(snapshot(), true);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.PENDING);

    answer.finish(MessageStatus.NO_CONTEXT, AnswerOutcome.interrupted("", "LOW_SIMILARITY"));
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.NO_CONTEXT);
    assertThat(answer.getStatusReason()).isEqualTo("LOW_SIMILARITY");
  }

  @Test
  void terminalAnswerCannotChangeAgain() {
    Message answer = pendingAnswer();
    answer.applyMeta(snapshot(), false);
    answer.finish(MessageStatus.COMPLETED, AnswerOutcome.interrupted("본문", null));

    assertThatThrownBy(
            () -> answer.finish(MessageStatus.FAILED, AnswerOutcome.interrupted("", "STALE")))
        .isInstanceOf(IllegalStateException.class);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.COMPLETED);
  }

  @Test
  void pendingCannotBecomePartial() {
    Message answer = pendingAnswer();

    assertThatThrownBy(
            () -> answer.finish(MessageStatus.PARTIAL, AnswerOutcome.interrupted("", "LENGTH")))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void questionHasNoStatus() {
    Conversation c = Conversation.single(1L, "q", "langchain_v03", NOW);
    Message question = Message.question(c, 1L, "q", 1);

    assertThat(question.getStatus()).isNull();
    assertThat(question.getQuotaCost()).isEqualTo((short) 1);
    assertThatThrownBy(() -> question.applyMeta(snapshot(), false))
        .isInstanceOf(IllegalStateException.class);
  }

  static Message pendingAnswer() {
    Conversation c = Conversation.single(1L, "q", "langchain_v03", NOW);
    return Message.pendingAnswer(c, 1L, "a1b2c3d4-0000-4000-8000-000000000001");
  }

  static AnswerSnapshot snapshot() {
    return new AnswerSnapshot(
        7L,
        "0123456789abcdef0123456789abcdef01234567",
        LocalDate.of(2026, 10, 5),
        new BigDecimal("0.8732"),
        null);
  }
}
