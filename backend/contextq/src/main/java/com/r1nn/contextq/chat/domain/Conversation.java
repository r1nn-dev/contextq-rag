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
import java.util.Objects;

/**
 * A learning session fixed to one version (SINGLE) or one version pair (COMPARE) (policy §6.1).
 *
 * <p>{@code mode} and the source keys have no setter and are not updatable (INV-10). {@code
 * updatedAt} moves only when an ASSISTANT message ends (list ordering, policy §6.1), so it is set
 * explicitly instead of by Hibernate.
 */
@Entity
@Table(name = "conversations")
public class Conversation {

  /** Message cap per conversation (50 turns, policy §6.1). */
  public static final int MAX_MESSAGES = 100;

  static final int TITLE_LENGTH = 40;

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "user_id", nullable = false, updatable = false)
  private Long userId;

  @Column(nullable = false, length = TITLE_LENGTH, updatable = false)
  private String title;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30, updatable = false)
  private ConversationMode mode;

  @Column(name = "source_key", length = 50, updatable = false)
  private String sourceKey;

  @Column(name = "source_key_a", length = 50, updatable = false)
  private String sourceKeyA;

  @Column(name = "source_key_b", length = 50, updatable = false)
  private String sourceKeyB;

  @Column(name = "message_count", nullable = false)
  private int messageCount;

  @Enumerated(EnumType.STRING)
  @Column(name = "last_message_status", length = 30)
  private MessageStatus lastMessageStatus;

  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected Conversation() {}

  private Conversation(
      Long userId,
      String question,
      ConversationMode mode,
      String sourceKey,
      String sourceKeyA,
      String sourceKeyB,
      Instant now) {
    this.userId = Objects.requireNonNull(userId);
    this.title = titleOf(question);
    this.mode = mode;
    this.sourceKey = sourceKey;
    this.sourceKeyA = sourceKeyA;
    this.sourceKeyB = sourceKeyB;
    this.messageCount = 0;
    this.createdAt = now;
    this.updatedAt = now;
  }

  /** New SINGLE conversation; the title is the first question (policy §6.1). */
  public static Conversation single(Long userId, String question, String sourceKey, Instant now) {
    return new Conversation(
        userId,
        question,
        ConversationMode.SINGLE,
        Objects.requireNonNull(sourceKey),
        null,
        null,
        now);
  }

  /** New COMPARE conversation (A = older, B = newer, policy §3.2). */
  public static Conversation compare(
      Long userId, String question, String sourceKeyA, String sourceKeyB, Instant now) {
    return new Conversation(
        userId,
        question,
        ConversationMode.COMPARE,
        null,
        Objects.requireNonNull(sourceKeyA),
        Objects.requireNonNull(sourceKeyB),
        now);
  }

  /** First 40 characters of the question with line breaks removed (policy §6.1). */
  static String titleOf(String question) {
    String flat = question.replaceAll("[\\r\\n]+", " ").strip();
    return flat.length() <= TITLE_LENGTH ? flat : flat.substring(0, TITLE_LENGTH);
  }

  public boolean isOwnedBy(Long requesterId) {
    return userId.equals(requesterId);
  }

  /** Whether {@code count} more messages still fit under the cap. */
  public boolean canAppend(int count) {
    return messageCount + count <= MAX_MESSAGES;
  }

  /** Counts the USER + ASSISTANT pair inserted for one question. */
  public void appendMessages(int count) {
    if (!canAppend(count)) {
      throw new IllegalStateException("conversation " + id + " is full");
    }
    messageCount += count;
  }

  /** ASSISTANT message ended: list ordering and status badge (policy §6.3 step 4). */
  public void recordAnswerEnded(MessageStatus status, Instant endedAt) {
    if (!status.isTerminal()) {
      throw new IllegalArgumentException("not a terminal status: " + status);
    }
    this.lastMessageStatus = status;
    this.updatedAt = endedAt;
  }

  public Long getId() {
    return id;
  }

  public Long getUserId() {
    return userId;
  }

  public String getTitle() {
    return title;
  }

  public ConversationMode getMode() {
    return mode;
  }

  public String getSourceKey() {
    return sourceKey;
  }

  public String getSourceKeyA() {
    return sourceKeyA;
  }

  public String getSourceKeyB() {
    return sourceKeyB;
  }

  public int getMessageCount() {
    return messageCount;
  }

  public MessageStatus getLastMessageStatus() {
    return lastMessageStatus;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
