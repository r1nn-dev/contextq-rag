package com.r1nn.contextq.chat.domain;

import java.util.List;

/**
 * Versions one question targets (policy §5.1, INV-10): one source in SINGLE mode, an ordered pair
 * in COMPARE mode (A = older, B = newer, policy §3.2).
 *
 * <p>A requested target may leave keys null (follow-up questions may omit the versions); the target
 * of a conversation always has them.
 */
public record QuestionTarget(
    ConversationMode mode, String sourceKey, String sourceKeyA, String sourceKeyB) {

  public static QuestionTarget single(String sourceKey) {
    return new QuestionTarget(ConversationMode.SINGLE, sourceKey, null, null);
  }

  public static QuestionTarget compare(String sourceKeyA, String sourceKeyB) {
    return new QuestionTarget(ConversationMode.COMPARE, null, sourceKeyA, sourceKeyB);
  }

  /** Fixed target of an existing conversation. */
  public static QuestionTarget of(Conversation conversation) {
    return new QuestionTarget(
        conversation.getMode(),
        conversation.getSourceKey(),
        conversation.getSourceKeyA(),
        conversation.getSourceKeyB());
  }

  public boolean isCompare() {
    return mode == ConversationMode.COMPARE;
  }

  /** Source keys this question searches, A before B in COMPARE mode. */
  public List<String> sourceKeys() {
    return isCompare() ? List.of(sourceKeyA, sourceKeyB) : List.of(sourceKey);
  }
}
