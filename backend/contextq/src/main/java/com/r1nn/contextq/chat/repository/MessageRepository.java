package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageStatus;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MessageRepository extends JpaRepository<Message, Long> {

  /**
   * Newest 6 messages (3 turns) of a conversation, newest first — the rewrite window of policy §5.2
   * (idx_msg_conv_created).
   */
  List<Message> findTop6ByConversation_IdOrderByCreatedAtDescIdDesc(Long conversationId);

  /** Conversation messages oldest first (idx_msg_conv_created, api-spec §4.2). */
  List<Message> findByConversation_IdOrderByCreatedAtAscIdAsc(Long conversationId);

  long countByConversation_IdAndRoleAndStatusIn(
      Long conversationId, MessageRole role, Collection<MessageStatus> statuses);

  /**
   * PENDING·STREAMING·PROCESSING answers of the conversation (INV-11). Call after {@link
   * ConversationRepository#findByIdForUpdate} in the same transaction.
   */
  default long countInProgress(Long conversationId) {
    return countByConversation_IdAndRoleAndStatusIn(
        conversationId, MessageRole.ASSISTANT, MessageStatus.inProgress());
  }

  /**
   * Answer row lock for the terminal UPDATE: the relay and the sweeper cannot both end the same
   * answer (INV-12 — the first one wins, the second sees a terminal status).
   */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select m from Message m where m.id = :id")
  Optional<Message> findByIdForUpdate(@Param("id") Long id);

  /** ASSISTANT answers in {@code statuses} whose last update is older than {@code threshold}. */
  @Query(
      "select m.id from Message m where m.role = com.r1nn.contextq.chat.domain.MessageRole.ASSISTANT"
          + " and m.status in :statuses and m.updatedAt < :threshold order by m.id")
  List<Long> findStuckAnswerIds(
      @Param("statuses") Collection<MessageStatus> statuses, @Param("threshold") Instant threshold);

  /**
   * Locks the user row so the daily-quota check and the question insert of one user are serialized
   * (policy §8.1). A new conversation has no conversation row to lock (INV-11 lock does not help).
   */
  @Query(value = "SELECT id FROM users WHERE id = :userId FOR UPDATE", nativeQuery = true)
  Long lockUserForQuota(@Param("userId") Long userId);

  /** Sum of USER {@code quota_cost} since {@code since} (idx_msg_user_quota, policy §8.1). */
  @Query(
      "select coalesce(sum(m.quotaCost), 0) from Message m where m.userId = :userId"
          + " and m.role = com.r1nn.contextq.chat.domain.MessageRole.USER"
          + " and m.createdAt >= :since")
  long sumQuotaCostSince(@Param("userId") Long userId, @Param("since") Instant since);
}
