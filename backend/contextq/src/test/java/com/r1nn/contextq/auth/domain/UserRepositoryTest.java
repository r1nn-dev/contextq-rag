package com.r1nn.contextq.auth.domain;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class UserRepositoryTest {

  @Autowired private UserRepository users;

  @Test
  void storesNormalizedEmailAndDefaults() {
    User saved = users.saveAndFlush(User.member("  Mixed.Case@Example.COM ", "$2a$10$hash"));

    User found = users.findByEmail("mixed.case@example.com").orElseThrow();
    assertThat(found.getId()).isEqualTo(saved.getId());
    assertThat(found.getRole()).isEqualTo(UserRole.ROLE_USER);
    assertThat(found.getStatus()).isEqualTo(UserStatus.ACTIVE);
    assertThat(found.getLoginFailedCount()).isZero();
    assertThat(found.getCreatedAt()).isNotNull();
    assertThat(users.existsByEmail("mixed.case@example.com")).isTrue();
  }

  @Test
  void adminFactoryUsesAdminRole() {
    assertThat(User.admin("admin@example.com", "$2a$10$hash").getRole())
        .isEqualTo(UserRole.ROLE_ADMIN);
  }
}
