package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.GuestSession;
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuestSessionRepository extends JpaRepository<GuestSession, Long> {

  Optional<GuestSession> findBySidHash(String sidHash);

  /** Sessions issued to one IP since {@code since} (GUEST_SESSION_LIMIT, policy §1.3). */
  long countByIpAddressAndCreatedAtAfter(String ipAddress, Instant since);

  /**
   * Atomic deduction (policy §1.3 차감 규칙, INV-16): one conditional UPDATE, no read-modify-write. The
   * fifth use marks the session EXHAUSTED.
   *
   * @return 1 when a question was charged, 0 when exhausted or expired
   */
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      value =
          "UPDATE guest_sessions SET used_count = used_count + 1,"
              + " status = CASE WHEN used_count + 1 >= 5 THEN 'EXHAUSTED' ELSE 'ACTIVE' END,"
              + " updated_at = :now"
              + " WHERE sid_hash = :sidHash AND used_count < 5 AND expires_at > :now",
      nativeQuery = true)
  int consume(@Param("sidHash") String sidHash, @Param("now") Instant now);

  /**
   * One refund after a server-side failure before {@code meta} (policy §1.3 환불 규칙). An EXHAUSTED
   * session becomes ACTIVE again (policy §10.3).
   */
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      value =
          "UPDATE guest_sessions SET used_count = used_count - 1, status = 'ACTIVE',"
              + " updated_at = :now WHERE sid_hash = :sidHash AND used_count > 0",
      nativeQuery = true)
  int refund(@Param("sidHash") String sidHash, @Param("now") Instant now);

  /** Physical delete of sessions expired before {@code threshold} (expiry + 24 h). */
  @Modifying
  @Query("delete from GuestSession s where s.expiresAt < :threshold")
  int deleteExpiredBefore(@Param("threshold") Instant threshold);
}
