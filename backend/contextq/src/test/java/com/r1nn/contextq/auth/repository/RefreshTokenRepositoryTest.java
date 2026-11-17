package com.r1nn.contextq.auth.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.RefreshToken;
import com.r1nn.contextq.auth.domain.TokenFamily;
import com.r1nn.contextq.auth.domain.User;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class RefreshTokenRepositoryTest {

  static final String HASH = "a".repeat(64);

  @Autowired private UserRepository users;
  @Autowired private TokenFamilyRepository families;
  @Autowired private RefreshTokenRepository tokens;

  @Test
  void storesFamilyAndHashedToken() {
    Instant now = Instant.now();
    TokenFamily family = families.save(TokenFamily.start(userId(), now, Duration.ofDays(7)));
    tokens.saveAndFlush(RefreshToken.issue(family, HASH, now));

    RefreshToken found = tokens.findByTokenHash(HASH).orElseThrow();
    assertThat(found.getStatus()).isEqualTo(RefreshToken.Status.ACTIVE);
    assertThat(found.getFamily().getExpiresAt()).isEqualTo(family.getExpiresAt());
    assertThat(families.findActive(family.getUserId(), now)).hasSize(1);
  }

  @Test
  void tokenHashIsUnique() {
    Instant now = Instant.now();
    TokenFamily family = families.save(TokenFamily.start(userId(), now, Duration.ofDays(7)));
    tokens.saveAndFlush(RefreshToken.issue(family, "b".repeat(64), now));

    assertThatThrownBy(() -> tokens.saveAndFlush(RefreshToken.issue(family, "b".repeat(64), now)))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void expiredFamilyIsNotActive() {
    Instant now = Instant.now();
    TokenFamily family = families.save(TokenFamily.start(userId(), now, Duration.ofDays(7)));

    assertThat(family.isExpiredAt(now.plus(Duration.ofDays(7)))).isTrue();
    assertThat(families.findActive(family.getUserId(), now.plus(Duration.ofDays(8)))).isEmpty();
  }

  private Long userId() {
    return users
        .save(User.member("rt" + System.nanoTime() + "@example.com", "$2a$10$hash"))
        .getId();
  }
}
