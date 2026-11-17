package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.domain.UserStatus;
import com.r1nn.contextq.auth.dto.LoginRequest;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.support.FixedClockConfiguration;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** policy §1.2: same failure for unknown/wrong, 5 failures in 15 min lock for 15 min. */
@Import({TestcontainersConfiguration.class, FixedClockConfiguration.class})
@SpringBootTest
class LoginServiceTest {

  static final String PASSWORD = "pass1234";

  @Autowired private LoginService loginService;
  @Autowired private SignupService signupService;
  @Autowired private UserRepository users;
  @Autowired private MutableClock clock;

  private String email;

  @BeforeEach
  void setUp() {
    email = "login" + System.nanoTime() + "@example.com";
    signupService.signup(new SignupRequest(email, PASSWORD));
  }

  @Test
  void correctPasswordAuthenticatesAndClearsFailures() {
    failTimes(2);

    LoginService.LoggedIn loggedIn =
        loginService.authenticate(new LoginRequest(" " + email.toUpperCase(), PASSWORD));

    assertThat(loggedIn.userId()).isEqualTo(user().getId());
    assertThat(user().getLoginFailedCount()).isZero();
    assertThat(user().getLoginFailedAt()).isNull();
  }

  @Test
  void unknownAccountAndWrongPasswordLookTheSame() {
    BusinessException unknown =
        failure(new LoginRequest("nobody" + System.nanoTime() + "@x.com", PASSWORD));
    BusinessException wrong = failure(new LoginRequest(email, "wrong1234"));

    assertThat(unknown.getErrorCode()).isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);
    assertThat(wrong.getErrorCode()).isEqualTo(unknown.getErrorCode());
    assertThat(wrong.getMessage()).isEqualTo(unknown.getMessage());
  }

  @Test
  void fifthFailureWithinWindowLocksFor15Minutes() {
    failTimes(4);
    assertThat(user().getLoginFailedCount()).isEqualTo((short) 4);

    BusinessException fifth = failure(new LoginRequest(email, "wrong1234"));
    assertThat(fifth.getErrorCode()).isEqualTo(ErrorCode.AUTH_LOCKED);
    assertThat(fifth.getHeaders()).containsEntry("Retry-After", "900");
    assertThat(user().getStatus()).isEqualTo(UserStatus.LOCKED);

    clock.advance(Duration.ofMinutes(10));
    BusinessException whileLocked = failure(new LoginRequest(email, PASSWORD));
    assertThat(whileLocked.getErrorCode()).isEqualTo(ErrorCode.AUTH_LOCKED);
    assertThat(whileLocked.getHeaders()).containsEntry("Retry-After", "300");

    clock.advance(Duration.ofMinutes(5));
    assertThat(loginService.authenticate(new LoginRequest(email, PASSWORD)).userId())
        .isEqualTo(user().getId());
    assertThat(user().getStatus()).isEqualTo(UserStatus.ACTIVE);
  }

  @Test
  void failuresSpreadBeyondWindowStartANewWindow() {
    failTimes(4);
    clock.advance(Duration.ofMinutes(15).plusSeconds(1));

    BusinessException next = failure(new LoginRequest(email, "wrong1234"));

    assertThat(next.getErrorCode()).isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);
    assertThat(user().getLoginFailedCount()).isEqualTo((short) 1);
  }

  private void failTimes(int times) {
    for (int i = 0; i < times; i++) {
      assertThat(failure(new LoginRequest(email, "wrong1234")).getErrorCode())
          .isEqualTo(ErrorCode.AUTH_INVALID_CREDENTIALS);
    }
  }

  private BusinessException failure(LoginRequest request) {
    Throwable thrown = catchThrowable(() -> loginService.authenticate(request));
    assertThat(thrown).isInstanceOf(BusinessException.class);
    return (BusinessException) thrown;
  }

  private User user() {
    return users.findByEmail(email).orElseThrow();
  }
}
