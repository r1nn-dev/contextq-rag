package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.MessageSource;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MessageSourceRepository extends JpaRepository<MessageSource, Long> {

  List<MessageSource> findByMessage_IdOrderByIdAsc(Long messageId);
}
