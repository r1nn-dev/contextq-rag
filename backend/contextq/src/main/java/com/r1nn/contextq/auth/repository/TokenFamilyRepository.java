package com.r1nn.contextq.auth.repository;

import com.r1nn.contextq.auth.domain.TokenFamily;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TokenFamilyRepository extends JpaRepository<TokenFamily, Long> {

  /** Serializes rotation, reuse detection and logout of one family (INV-15). */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select f from TokenFamily f where f.id = :id")
  Optional<TokenFamily> findByIdForUpdate(@Param("id") Long id);

  /** Unexpired ACTIVE families of a user, oldest first (cap of 10, policy §1.2). */
  @Query(
      "select f from TokenFamily f where f.userId = :userId and f.status ="
          + " com.r1nn.contextq.auth.domain.TokenFamily.Status.ACTIVE and f.expiresAt > :now"
          + " order by f.createdAt asc, f.id asc")
  List<TokenFamily> findActive(@Param("userId") Long userId, @Param("now") Instant now);

  /** Physical delete of families expired before {@code threshold} (tokens first, FK). */
  @Modifying
  @Query("delete from TokenFamily f where f.expiresAt < :threshold")
  int deleteExpiredBefore(@Param("threshold") Instant threshold);
}
