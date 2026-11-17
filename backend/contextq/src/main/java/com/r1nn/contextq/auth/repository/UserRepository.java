package com.r1nn.contextq.auth.repository;

import com.r1nn.contextq.auth.domain.User;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {

  /**
   * @param email already normalized (trim, lower case)
   */
  Optional<User> findByEmail(String email);

  boolean existsByEmail(String email);
}
