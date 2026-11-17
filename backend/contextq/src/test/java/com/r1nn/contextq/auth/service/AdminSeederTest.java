package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.auth.service.AdminSeeder.Result;
import com.r1nn.contextq.global.config.AdminSeedProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.password.PasswordEncoder;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
class AdminSeederTest {

  @Autowired private UserRepository users;
  @Autowired private PasswordEncoder passwordEncoder;

  @Test
  void seedIsIdempotent() {
    String email = "Admin" + System.nanoTime() + "@Example.com";
    AdminSeeder seeder = seeder(email, passwordEncoder.encode("admin1234"));

    assertThat(seeder.seed()).isEqualTo(Result.CREATED);
    assertThat(seeder.seed()).isEqualTo(Result.EXISTS);

    assertThat(users.findByEmail(email.toLowerCase()))
        .hasValueSatisfying(u -> assertThat(u.getRole()).isEqualTo(UserRole.ROLE_ADMIN));
  }

  @Test
  void missingValuesDisableSeed() {
    assertThat(seeder("", "x").seed()).isEqualTo(Result.DISABLED);
    assertThat(seeder("a@example.com", null).seed()).isEqualTo(Result.DISABLED);
  }

  @Test
  void plainPasswordIsRefused() {
    String email = "plain" + System.nanoTime() + "@example.com";

    assertThat(seeder(email, "admin1234").seed()).isEqualTo(Result.INVALID_HASH);
    assertThat(users.existsByEmail(email)).isFalse();
  }

  private AdminSeeder seeder(String email, String hash) {
    return new AdminSeeder(users, new AdminSeedProperties(email, hash));
  }
}
