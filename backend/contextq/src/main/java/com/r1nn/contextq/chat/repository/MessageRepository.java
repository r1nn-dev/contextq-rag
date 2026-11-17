package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageStatus;
import java.util.Collection;
import org.springframework.data.jpa.repository.JpaRepository;

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
}
