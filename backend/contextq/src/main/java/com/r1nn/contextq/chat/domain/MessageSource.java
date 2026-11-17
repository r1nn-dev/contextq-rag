package com.r1nn.contextq.chat.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * [IMMUTABLE] value snapshot of one cited source (db-design §3.8, INV-13).
 *
 * <p>Copied from {@code meta.sources}, so history survives index replacement and PURGED runs.
 */
@Entity
@Immutable
@Table(name = "message_sources")
public class MessageSource {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "message_id", nullable = false, updatable = false)
  private Message message;

  @Column(name = "source_key", nullable = false, length = 50)
  private String sourceKey;

  /** "1", "2", … (single) or "A1", "B2", … (compare). */
  @Column(name = "rank_label", nullable = false, length = 5)
  private String rankLabel;

  /** Not carried by the SSE contract; null when relayed (db-design §3.8). */
  @JdbcTypeCode(SqlTypes.CHAR)
  @Column(name = "chunk_id", length = 32)
  private String chunkId;

  @Column(name = "heading_path", nullable = false, columnDefinition = "TEXT")
  private String headingPath;

  @Column(nullable = false, columnDefinition = "TEXT")
  private String permalink;

  @Column(name = "site_url", columnDefinition = "TEXT")
  private String siteUrl;

  @Column(nullable = false, precision = 5, scale = 4)
  private BigDecimal similarity;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected MessageSource() {}

  public static MessageSource of(
      Message message,
      String sourceKey,
      String rankLabel,
      String headingPath,
      String permalink,
      String siteUrl,
      BigDecimal similarity) {
    MessageSource s = new MessageSource();
    s.message = message;
    s.sourceKey = sourceKey;
    s.rankLabel = rankLabel;
    s.headingPath = headingPath;
    s.permalink = permalink;
    s.siteUrl = siteUrl;
    s.similarity = similarity;
    return s;
  }

  public Long getId() {
    return id;
  }

  public Message getMessage() {
    return message;
  }

  public String getSourceKey() {
    return sourceKey;
  }

  public String getRankLabel() {
    return rankLabel;
  }

  public String getChunkId() {
    return chunkId;
  }

  public String getHeadingPath() {
    return headingPath;
  }

  public String getPermalink() {
    return permalink;
  }

  public String getSiteUrl() {
    return siteUrl;
  }

  public BigDecimal getSimilarity() {
    return similarity;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
