package com.r1nn.contextq.chat.dto;

import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.ConversationStatus;
import com.r1nn.contextq.chat.domain.MessageStatus;
import java.time.Instant;

/**
 * One row of {@code GET /api/v1/conversations} (api-spec §4.1).
 *
 * @param versionLabel SINGLE: source label; COMPARE: {@code "v0.3 vs v1.x"}
 * @param lastMessageStatus latest ASSISTANT status; null while only USER messages exist
 * @param status derived, not stored
 */
public record ConversationSummaryResponse(
    Long conversationId,
    String title,
    ConversationMode mode,
    String sourceKey,
    String sourceKeyA,
    String sourceKeyB,
    String versionLabel,
    int messageCount,
    MessageStatus lastMessageStatus,
    ConversationStatus status,
    Instant updatedAt) {

  public static ConversationSummaryResponse from(
      Conversation c, String versionLabel, ConversationStatus status) {
    return new ConversationSummaryResponse(
        c.getId(),
        c.getTitle(),
        c.getMode(),
        c.getSourceKey(),
        c.getSourceKeyA(),
        c.getSourceKeyB(),
        versionLabel,
        c.getMessageCount(),
        c.getLastMessageStatus(),
        status,
        c.getUpdatedAt());
  }
}
