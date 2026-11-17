package com.r1nn.contextq.auth.repository;

import com.r1nn.contextq.auth.domain.User;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

  /**
   * @param email already normalized (trim, lower case)
   */
  Optional<User> findByEmail(String email);

  boolean existsByEmail(String email);

  /** Login takes the user row lock so concurrent wrong passwords are counted one by one. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select u from User u where u.email = :email")
  Optional<User> findByEmailForUpdate(@Param("email") String email);
}
