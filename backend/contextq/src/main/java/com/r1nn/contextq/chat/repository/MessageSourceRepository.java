package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.MessageSource;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MessageSourceRepository extends JpaRepository<MessageSource, Long> {

  List<MessageSource> findByMessage_IdOrderByIdAsc(Long messageId);

  /** Every cited source of a conversation in one query (detail view, no per-message N+1). */
  List<MessageSource> findByMessage_Conversation_IdOrderByIdAsc(Long conversationId);
}
