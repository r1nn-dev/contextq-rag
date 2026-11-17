package com.r1nn.contextq.chat.domain;

/**
 * Derived conversation state, never stored (db-design §3.6 파생 상태).
 *
 * <p>{@code OPEN}: follow-up questions are accepted. {@code READ_ONLY}: 100 messages reached or a
 * source of the conversation is inactive.
 */
public enum ConversationStatus {
  OPEN,
  READ_ONLY
}
