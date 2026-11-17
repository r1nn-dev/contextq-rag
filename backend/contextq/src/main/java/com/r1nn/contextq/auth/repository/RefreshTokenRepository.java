package com.r1nn.contextq.auth.repository;

import com.r1nn.contextq.auth.domain.RefreshToken;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, Long> {

  Optional<RefreshToken> findByTokenHash(String tokenHash);

  /**
   * Family of a presented token without loading the token itself, so the token is read only after
   * the family lock (fresh state, INV-15).
   */
  @Query("select t.family.id from RefreshToken t where t.tokenHash = :hash")
  Optional<Long> findFamilyIdByTokenHash(@Param("hash") String tokenHash);

  List<RefreshToken> findByFamily_Id(Long familyId);

  long countByFamily_IdAndStatus(Long familyId, RefreshToken.Status status);

  /** Tokens of families expired before {@code threshold} (deleted before their families). */
  @Modifying
  @Query(
      "delete from RefreshToken t where t.family.id in"
          + " (select f.id from TokenFamily f where f.expiresAt < :threshold)")
  int deleteOfFamiliesExpiredBefore(@Param("threshold") Instant threshold);
}
