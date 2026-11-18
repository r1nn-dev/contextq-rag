package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.domain.UserStatus;
import com.r1nn.contextq.auth.dto.LoginRequest;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.account.AccountUnlocker;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.support.FixedClockConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** Admin unlock through the common interface (policy §10.3, api-spec §5.4). */
@Import({TestcontainersConfiguration.class, FixedClockConfiguration.class})
@SpringBootTest
class AccountUnlockServiceTest {

  static final String PASSWORD = "pass1234";

  @Autowired private AccountUnlocker unlocker;
  @Autowired private LoginService loginService;
  @Autowired private SignupService signupService;
  @Autowired private UserRepository users;

  private String email;

  @BeforeEach
  void setUp() {
    email = "unlock" + System.nanoTime() + "@example.com";
    signupService.signup(new SignupRequest(email, PASSWORD));
  }

  @Test
  void lockedAccountCanLogInRightAfterUnlock() {
    for (int i = 0; i < User.MAX_FAILURES; i++) {
      catchThrowable(() -> loginService.authenticate(new LoginRequest(email, "wrong1234")));
    }
    assertThat(user().getStatus()).isEqualTo(UserStatus.LOCKED);

    unlocker.unlock(user().getId());

    User unlocked = user();
    assertThat(unlocked.getStatus()).isEqualTo(UserStatus.ACTIVE);
    assertThat(unlocked.getLoginFailedCount()).isZero();
    assertThat(unlocked.getLockedAt()).isNull();
    assertThat(unlocked.getLoginFailedAt()).isNull();
    assertThat(loginService.authenticate(new LoginRequest(email, PASSWORD)).userId())
        .isEqualTo(unlocked.getId());
  }

  @Test
  void unlockingAnActiveAccountChangesNothing() {
    unlocker.unlock(user().getId());

    assertThat(user().getStatus()).isEqualTo(UserStatus.ACTIVE);
  }

  @Test
  void unknownUserIsNotFound() {
    assertThatThrownBy(() -> unlocker.unlock(Long.MAX_VALUE))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.USER_NOT_FOUND));
  }

  private User user() {
    return users.findByEmail(email).orElseThrow();
  }
}
