package com.r1nn.contextq.chat.dto;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.common.error.BusinessException;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ChatStreamRequestTest {

  private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

  @Test
  void validSingleRequestPasses() {
    ChatStreamRequest req = single("  Agent 생성 방법  ", "langchain_v03");

    assertThat(validator.validate(req)).isEmpty();
    assertThat(req.trimmedQuestion()).isEqualTo("Agent 생성 방법");
    assertThatCode(req::requireModeFields).doesNotThrowAnyException();
  }

  @Test
  void blankQuestionIsRejected() {
    assertThat(fields(single("   ", "langchain_v03"))).containsExactly("question");
  }

  @Test
  void questionLimitCountsTrimmedCharacters() {
    String exactly1000 = "가".repeat(1000);

    assertThat(validator.validate(single("  " + exactly1000 + "  ", "langchain_v03"))).isEmpty();
    assertThat(fields(single(exactly1000 + "가", "langchain_v03"))).containsExactly("question");
  }

  @Test
  void missingModeIsRejected() {
    ChatStreamRequest req = new ChatStreamRequest(null, "q", null, "langchain_v03", null, null);

    assertThat(fields(req)).containsExactly("mode");
  }

  @Test
  void malformedSourceKeyIsRejected() {
    assertThat(fields(single("q", "LangChain v0.3"))).containsExactly("sourceKey");
  }

  @Test
  void newSingleConversationNeedsSourceKey() {
    ChatStreamRequest req = single("q", null);

    assertThatThrownBy(req::requireModeFields)
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getDetails().getFirst().field()).isEqualTo("sourceKey"));
  }

  @Test
  void existingConversationMayOmitSourceKey() {
    ChatStreamRequest req =
        new ChatStreamRequest(42L, "q", ConversationMode.SINGLE, null, null, null);

    assertThatCode(req::requireModeFields).doesNotThrowAnyException();
  }

  @Test
  void newCompareConversationNeedsTwoDifferentVersions() {
    assertThatCode(compare(null, null, "langchain_v03", "langchain_v1x")::requireModeFields)
        .doesNotThrowAnyException();
    assertInvalidField(compare(null, null, "langchain_v03", null), "sourceKeyB");
    assertInvalidField(compare(null, null, null, "langchain_v1x"), "sourceKeyA");
    assertInvalidField(compare(null, null, "langchain_v03", "langchain_v03"), "sourceKeyB");
  }

  @Test
  void existingCompareConversationMayOmitVersions() {
    assertThatCode(compare(42L, null, null, null)::requireModeFields).doesNotThrowAnyException();
  }

  @Test
  void versionFieldsOfTheOtherModeAreRejected() {
    assertInvalidField(
        compare(null, "langchain_v03", "langchain_v03", "langchain_v1x"), "sourceKey");
    assertInvalidField(
        new ChatStreamRequest(
            null, "q", ConversationMode.SINGLE, "langchain_v03", "langchain_v03", null),
        "sourceKeyA");
  }

  @Test
  void requestedTargetFollowsTheMode() {
    assertThat(compare(null, null, "langchain_v03", "langchain_v1x").requestedTarget().sourceKeys())
        .containsExactly("langchain_v03", "langchain_v1x");
    assertThat(single("q", "langchain_v03").requestedTarget().sourceKeys())
        .containsExactly("langchain_v03");
  }

  static ChatStreamRequest compare(Long conversationId, String sourceKey, String a, String b) {
    return new ChatStreamRequest(conversationId, "q", ConversationMode.COMPARE, sourceKey, a, b);
  }

  private static void assertInvalidField(ChatStreamRequest req, String field) {
    assertThatThrownBy(req::requireModeFields)
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getDetails().getFirst().field()).isEqualTo(field));
  }

  static ChatStreamRequest single(String question, String sourceKey) {
    return new ChatStreamRequest(null, question, ConversationMode.SINGLE, sourceKey, null, null);
  }

  private Set<String> fields(ChatStreamRequest req) {
    return validator.validate(req).stream()
        .map(ConstraintViolation::getPropertyPath)
        .map(Object::toString)
        .collect(java.util.stream.Collectors.toSet());
  }
}
