package com.r1nn.contextq.chat.dto;

import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.ConversationStatus;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

/**
 * {@code GET /api/v1/conversations/{conversationId}} body (api-spec §4.2 응답 규칙).
 *
 * @param messages oldest first; {@link UserMessage} or {@link AssistantMessage}
 */
public record ConversationDetailResponse(
    Long conversationId,
    String title,
    ConversationMode mode,
    String sourceKey,
    String sourceKeyA,
    String sourceKeyB,
    ConversationStatus status,
    int messageCount,
    Instant createdAt,
    Instant updatedAt,
    List<MessageItem> messages) {

  public static ConversationDetailResponse of(
      Conversation c, ConversationStatus status, List<MessageItem> messages) {
    return new ConversationDetailResponse(
        c.getId(),
        c.getTitle(),
        c.getMode(),
        c.getSourceKey(),
        c.getSourceKeyA(),
        c.getSourceKeyB(),
        status,
        c.getMessageCount(),
        c.getCreatedAt(),
        c.getUpdatedAt(),
        messages);
  }

  /** One message; serialized by its concrete record type. */
  public sealed interface MessageItem permits UserMessage, AssistantMessage {}

  public record UserMessage(Long messageId, MessageRole role, String content, Instant createdAt)
      implements MessageItem {

    public static UserMessage from(Message m) {
      return new UserMessage(m.getId(), m.getRole(), m.getContent(), m.getCreatedAt());
    }
  }

  /**
   * @param content empty until the answer ends (tokens are stored once, policy §6.3)
   * @param snapshot null when the answer ended before {@code meta}
   * @param usage null without token counts
   * @param latency null when all five values are missing
   */
  public record AssistantMessage(
      Long messageId,
      MessageRole role,
      String content,
      MessageStatus status,
      String statusReason,
      String requestId,
      String rewrittenQuery,
      Snapshot snapshot,
      Usage usage,
      Latency latency,
      List<SourceItem> sources,
      Instant createdAt,
      Instant updatedAt)
      implements MessageItem {

    /**
     * @param versionLabel label of the conversation source (api-spec §4.1 규칙)
     * @param cited sources of this message in rank order
     */
    public static AssistantMessage from(Message m, String versionLabel, List<MessageSource> cited) {
      return new AssistantMessage(
          m.getId(),
          m.getRole(),
          m.getContent() != null ? m.getContent() : "",
          m.getStatus(),
          m.getStatusReason(),
          m.getRequestId(),
          m.getRewrittenQuery(),
          m.getCommitSha() != null
              ? new Snapshot(versionLabel, m.getCommitSha(), m.getIngestedAt())
              : null,
          Usage.of(m.getPromptTokens(), m.getCompletionTokens()),
          Latency.of(
              m.getRewriteMs(), m.getEmbedMs(), m.getRetrieveMs(), m.getTtftMs(), m.getTotalMs()),
          cited.stream().map(SourceItem::from).toList(),
          m.getCreatedAt(),
          m.getUpdatedAt());
    }
  }

  /** Index snapshot copied at {@code meta} time (INV-13). */
  public record Snapshot(String versionLabel, String commitSha, LocalDate ingestedAt) {}

  public record Usage(Integer prompt, Integer completion) {

    static Usage of(Integer prompt, Integer completion) {
      return prompt == null && completion == null ? null : new Usage(prompt, completion);
    }
  }

  public record Latency(
      Integer rewriteMs, Integer embedMs, Integer retrieveMs, Integer ttftMs, Integer totalMs) {

    static Latency of(
        Integer rewriteMs, Integer embedMs, Integer retrieveMs, Integer ttftMs, Integer totalMs) {
      if (rewriteMs == null
          && embedMs == null
          && retrieveMs == null
          && ttftMs == null
          && totalMs == null) {
        return null;
      }
      return new Latency(rewriteMs, embedMs, retrieveMs, ttftMs, totalMs);
    }
  }

  /**
   * @param rank sequence number of {@code rankLabel} ("2" and "B2" → 2)
   */
  public record SourceItem(
      Integer rank,
      String rankLabel,
      String headingPath,
      String permalink,
      String siteUrl,
      BigDecimal similarity) {

    static SourceItem from(MessageSource s) {
      return new SourceItem(
          rankOf(s.getRankLabel()),
          s.getRankLabel(),
          s.getHeadingPath(),
          s.getPermalink(),
          s.getSiteUrl(),
          s.getSimilarity());
    }

    static Integer rankOf(String rankLabel) {
      String digits = rankLabel.replaceAll("\\D", "");
      return digits.isEmpty() ? null : Integer.valueOf(digits);
    }
  }
}
