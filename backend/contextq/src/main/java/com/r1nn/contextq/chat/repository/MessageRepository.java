package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageStatus;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MessageRepository extends JpaRepository<Message, Long> {

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
}
