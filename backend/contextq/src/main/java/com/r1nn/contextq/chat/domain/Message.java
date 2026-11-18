package com.r1nn.contextq.chat.domain;

import com.r1nn.contextq.domain.BaseTimeEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * USER question or ASSISTANT answer (db-design §3.7).
 *
 * <p>ASSISTANT status changes only through {@link #transitionTo}, which enforces policy §10.2
 * (INV-12). Retrieval and generation values are copied, not referenced (INV-13). Compare-mode
 * columns are mapped by the compare issue.
 */
@Entity
@Table(name = "messages")
public class Message extends BaseTimeEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "conversation_id", nullable = false, updatable = false)
  private Conversation conversation;

  @Column(name = "user_id", nullable = false, updatable = false)
  private Long userId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30, updatable = false)
  private MessageRole role;

  @Column(columnDefinition = "TEXT")
  private String content;

  @Column(name = "quota_cost")
  private Short quotaCost;

  @Column(name = "request_id", length = 36)
  private String requestId;

  @Enumerated(EnumType.STRING)
  @Column(length = 30)
  private MessageStatus status;

  @Column(name = "status_reason", length = 50)
  private String statusReason;

  @Column(name = "finish_reason", length = 20)
  private String finishReason;

  @Column(name = "rewritten_query", length = 200)
  private String rewrittenQuery;

  @Enumerated(EnumType.STRING)
  @Column(name = "rewrite_status", length = 20)
  private RewriteStatus rewriteStatus;

  @Column(name = "ingest_run_id")
  private Long ingestRunId;

  @JdbcTypeCode(SqlTypes.CHAR)
  @Column(name = "commit_sha", length = 40)
  private String commitSha;

  @Column(name = "ingested_at")
  private LocalDate ingestedAt;

  @Column(name = "top1_similarity", precision = 5, scale = 4)
  private BigDecimal top1Similarity;

  @Column(length = 50)
  private String model;

  @Column(name = "prompt_version", length = 50)
  private String promptVersion;

  @Column(name = "prompt_tokens")
  private Integer promptTokens;

  @Column(name = "completion_tokens")
  private Integer completionTokens;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "invalid_citations", columnDefinition = "JSONB")
  private String invalidCitations;

  @Column(name = "rewrite_ms")
  private Integer rewriteMs;

  @Column(name = "embed_ms")
  private Integer embedMs;

  @Column(name = "retrieve_ms")
  private Integer retrieveMs;

  @Column(name = "ttft_ms")
  private Integer ttftMs;

  @Column(name = "total_ms")
  private Integer totalMs;

  protected Message() {}

  /**
   * USER question with its daily quota cost (SINGLE = 1, COMPARE = 2; policy §8.1).
   *
   * @param content question text after trim
   */
  public static Message question(
      Conversation conversation, Long userId, String content, int quotaCost) {
    Message m = new Message();
    m.conversation = conversation;
    m.userId = userId;
    m.role = MessageRole.USER;
    m.content = content;
    m.quotaCost = (short) quotaCost;
    return m;
  }

  /** ASSISTANT answer accepted without history: no rewrite ({@code SKIPPED}). */
  public static Message pendingAnswer(Conversation conversation, Long userId, String requestId) {
    return pendingAnswer(conversation, userId, requestId, false);
  }

  /**
   * ASSISTANT answer accepted for processing (policy §6.3 step 1).
   *
   * @param rewriteRequested history was sent, so the rewrite outcome is known only at {@code meta}
   */
  public static Message pendingAnswer(
      Conversation conversation, Long userId, String requestId, boolean rewriteRequested) {
    Message m = new Message();
    m.conversation = conversation;
    m.userId = userId;
    m.role = MessageRole.ASSISTANT;
    m.requestId = requestId;
    m.status = MessageStatus.PENDING;
    m.rewriteStatus = rewriteRequested ? null : RewriteStatus.SKIPPED;
    return m;
  }

  /**
   * {@code meta} received (policy §6.3 step 2): copy the snapshot. With context the answer moves to
   * STREAMING; a NO_CONTEXT meta keeps PENDING until {@code done(NO_CONTEXT)} (policy §10.2).
   */
  public void applyMeta(AnswerSnapshot snapshot, boolean noContext) {
    requireAssistant();
    this.ingestRunId = snapshot.ingestRunId();
    this.commitSha = snapshot.commitSha();
    this.ingestedAt = snapshot.ingestedAt();
    this.top1Similarity = snapshot.top1Similarity();
    this.rewrittenQuery = snapshot.rewrittenQuery();
    if (rewriteStatus == null) { // history was sent: a rewritten query means the rewrite worked
      this.rewriteStatus =
          snapshot.rewrittenQuery() != null ? RewriteStatus.OK : RewriteStatus.FALLBACK;
    }
    if (!noContext) {
      transitionTo(MessageStatus.STREAMING);
    }
  }

  /** Single terminal UPDATE (policy §6.3 step 4). */
  public void finish(MessageStatus terminal, AnswerOutcome outcome) {
    requireAssistant();
    if (!terminal.isTerminal()) {
      throw new IllegalArgumentException("not a terminal status: " + terminal);
    }
    transitionTo(terminal);
    this.content = outcome.content();
    this.statusReason = outcome.statusReason();
    this.finishReason = outcome.finishReason();
    this.model = outcome.model();
    this.promptVersion = outcome.promptVersion();
    this.promptTokens = outcome.promptTokens();
    this.completionTokens = outcome.completionTokens();
    this.invalidCitations = outcome.invalidCitationsJson();
    this.rewriteMs = outcome.rewriteMs();
    this.embedMs = outcome.embedMs();
    this.retrieveMs = outcome.retrieveMs();
    this.ttftMs = outcome.ttftMs();
    this.totalMs = outcome.totalMs();
  }

  /**
   * Status change guarded by policy §10.2.
   *
   * @throws IllegalStateException when the pair is not in the table (incl. any terminal → x)
   */
  void transitionTo(MessageStatus next) {
    if (!MessageStatus.canTransition(status, next)) {
      throw new IllegalStateException(
          "message " + id + " cannot move from " + status + " to " + next);
    }
    this.status = next;
  }

  private void requireAssistant() {
    if (role != MessageRole.ASSISTANT) {
      throw new IllegalStateException("only ASSISTANT messages have a status");
    }
  }

  public Long getId() {
    return id;
  }

  public Conversation getConversation() {
    return conversation;
  }

  public Long getUserId() {
    return userId;
  }

  public MessageRole getRole() {
    return role;
  }

  public String getContent() {
    return content;
  }

  public Short getQuotaCost() {
    return quotaCost;
  }

  public String getRequestId() {
    return requestId;
  }

  public MessageStatus getStatus() {
    return status;
  }

  public String getStatusReason() {
    return statusReason;
  }

  public String getFinishReason() {
    return finishReason;
  }

  public String getRewrittenQuery() {
    return rewrittenQuery;
  }

  public RewriteStatus getRewriteStatus() {
    return rewriteStatus;
  }

  public Long getIngestRunId() {
    return ingestRunId;
  }

  public String getCommitSha() {
    return commitSha;
  }

  public LocalDate getIngestedAt() {
    return ingestedAt;
  }

  public BigDecimal getTop1Similarity() {
    return top1Similarity;
  }

  public String getModel() {
    return model;
  }

  public String getPromptVersion() {
    return promptVersion;
  }

  public Integer getPromptTokens() {
    return promptTokens;
  }

  public Integer getCompletionTokens() {
    return completionTokens;
  }

  public String getInvalidCitations() {
    return invalidCitations;
  }

  public Integer getRewriteMs() {
    return rewriteMs;
  }

  public Integer getEmbedMs() {
    return embedMs;
  }

  public Integer getRetrieveMs() {
    return retrieveMs;
  }

  public Integer getTtftMs() {
    return ttftMs;
  }

  public Integer getTotalMs() {
    return totalMs;
  }
}
