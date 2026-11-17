package com.r1nn.contextq.chat.domain;

/**
 * Values written by the single terminal UPDATE of an ASSISTANT message (policy §6.3 step 4).
 *
 * @param content accumulated answer text (tokens joined); empty when no token arrived
 * @param statusReason policy §10.2 reason, null for COMPLETED
 * @param finishReason OpenAI finish reason ({@code stop}, {@code length}), null when not called
 * @param model actual model name from the {@code done} event (INV-13)
 * @param promptVersion prompt file name from the {@code done} event (INV-13)
 * @param invalidCitationsJson JSON array of out-of-range citation numbers, null when unknown
 */
public record AnswerOutcome(
    String content,
    String statusReason,
    String finishReason,
    String model,
    String promptVersion,
    Integer promptTokens,
    Integer completionTokens,
    String invalidCitationsJson,
    Integer rewriteMs,
    Integer embedMs,
    Integer retrieveMs,
    Integer ttftMs,
    Integer totalMs) {

  /** Outcome with only text and reason (client abort, timeout, upstream error). */
  public static AnswerOutcome interrupted(String content, String statusReason) {
    return new AnswerOutcome(
        content, statusReason, null, null, null, null, null, null, null, null, null, null, null);
  }
}
