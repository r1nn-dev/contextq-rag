package com.r1nn.contextq.chat.dto;

import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.common.error.BusinessException;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;

/**
 * {@code POST /api/v1/chat/stream} body (api-spec §3.1, policy §5.1).
 *
 * <p>New conversation: {@code sourceKey} is required for SINGLE. Existing conversation: {@code
 * conversationId} alone is enough; version fields, when present, must match the conversation
 * (checked by the service). COMPARE is rejected until the compare issue.
 *
 * @param conversationId null to start a new conversation
 * @param question trimmed before use; 1~1,000 characters
 */
public record ChatStreamRequest(
    @Positive(message = "대화 ID는 양수여야 합니다.") Long conversationId,
    @QuestionText String question,
    @NotNull(message = "모드는 필수입니다.") ConversationMode mode,
    @Pattern(regexp = SOURCE_KEY, message = "소스 키 형식이 올바르지 않습니다.") String sourceKey,
    @Pattern(regexp = SOURCE_KEY, message = "소스 키 형식이 올바르지 않습니다.") String sourceKeyA,
    @Pattern(regexp = SOURCE_KEY, message = "소스 키 형식이 올바르지 않습니다.") String sourceKeyB) {

  /** Same shape as the contract schema ({@code ^[a-z0-9_]+$}), max 50 (db-design §3.6). */
  static final String SOURCE_KEY = "^[a-z0-9_]{1,50}$";

  /** Trimmed question text actually stored and sent to ai-server. */
  public String trimmedQuestion() {
    return question.strip();
  }

  /**
   * Mode rules that Bean Validation cannot express per field.
   *
   * @throws BusinessException {@code INVALID_REQUEST} with the offending field
   */
  public void requireSupportedMode() {
    if (mode == ConversationMode.COMPARE) {
      throw BusinessException.invalidField("mode", "비교 모드는 아직 지원하지 않습니다.");
    }
    if (conversationId == null && (sourceKey == null || sourceKey.isBlank())) {
      throw BusinessException.invalidField("sourceKey", "단일 모드에는 소스 키가 필요합니다.");
    }
  }
}
