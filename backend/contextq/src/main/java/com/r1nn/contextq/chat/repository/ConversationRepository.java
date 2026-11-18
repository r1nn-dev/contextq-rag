package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.Conversation;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationRepository extends JpaRepository<Conversation, Long> {

  /**
   * {@code SELECT … FOR UPDATE} on the conversation row (INV-11, db-design §5).
   *
   * <p>Concurrent questions to the same conversation wait here until the first transaction commits,
   * so the in-progress count that follows is serialized.
   */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select c from Conversation c where c.id = :id")
  Optional<Conversation> findByIdForUpdate(@Param("id") Long id);

  /** First page of the owner's list, newest {@code updated_at} first (idx_conv_user_updated). */
  List<Conversation> findByUserIdOrderByUpdatedAtDescIdDesc(Long userId, Limit limit);

  /** Next page: conversations updated strictly before the cursor (api-spec §4.1 {@code before}). */
  List<Conversation> findByUserIdAndUpdatedAtBeforeOrderByUpdatedAtDescIdDesc(
      Long userId, Instant before, Limit limit);
}
