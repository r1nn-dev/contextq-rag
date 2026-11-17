package com.r1nn.contextq.chat.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * [IMMUTABLE] one guest answer for cost and dashboard aggregation (db-design §3.5, policy §6.3 step
 * 5). Guest conversations themselves are never stored.
 */
@Entity
@Immutable
@Table(name = "guest_usage_logs")
public class GuestUsageLog {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @JdbcTypeCode(SqlTypes.CHAR)
  @Column(name = "sid_hash", nullable = false, length = 64)
  private String sidHash;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private MessageStatus status;

  @Column(name = "prompt_tokens")
  private Integer promptTokens;

  @Column(name = "completion_tokens")
  private Integer completionTokens;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  protected GuestUsageLog() {}

  /**
   * @param status terminal status (same model as ASSISTANT messages, policy §10.2)
   */
  public static GuestUsageLog of(
      String sidHash,
      MessageStatus status,
      Integer promptTokens,
      Integer completionTokens,
      Instant now) {
    if (!status.isTerminal()) {
      throw new IllegalArgumentException("usage log needs a terminal status: " + status);
    }
    GuestUsageLog log = new GuestUsageLog();
    log.sidHash = sidHash;
    log.status = status;
    log.promptTokens = promptTokens;
    log.completionTokens = completionTokens;
    log.createdAt = now;
    return log;
  }

  public String getSidHash() {
    return sidHash;
  }

  public MessageStatus getStatus() {
    return status;
  }

  public Integer getPromptTokens() {
    return promptTokens;
  }

  public Integer getCompletionTokens() {
    return completionTokens;
  }
}
