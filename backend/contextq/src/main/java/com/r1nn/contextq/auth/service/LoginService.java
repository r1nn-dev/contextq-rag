package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.auth.dto.LoginRequest;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Password login with account lock (api-spec §1.2, policy §1.2).
 *
 * <ul>
 *   <li>Unknown email and wrong password answer the same {@code AUTH_INVALID_CREDENTIALS}; an
 *       unknown email still runs one BCrypt comparison so timing does not reveal the account.
 *   <li>The fifth failure within 15 minutes of the first locks the account for 15 minutes ({@code
 *       AUTH_LOCKED} + {@code Retry-After}).
 * </ul>
 *
 * <p>Failures are thrown as exceptions but must be committed, hence {@code noRollbackFor}.
 */
@Service
public class LoginService {

  private final UserRepository users;
  private final PasswordEncoder passwordEncoder;
  private final Clock clock;
  private final String dummyHash;

  public LoginService(UserRepository users, PasswordEncoder passwordEncoder, Clock clock) {
    this.users = users;
    this.passwordEncoder = passwordEncoder;
    this.clock = clock;
    this.dummyHash = passwordEncoder.encode("timing-equalizer-not-a-password-1");
  }

  /** Verified account. */
  public record LoggedIn(Long userId, UserRole role) {}

  /**
   * @throws BusinessException {@code AUTH_INVALID_CREDENTIALS} or {@code AUTH_LOCKED}
   */
  @Transactional(noRollbackFor = BusinessException.class)
  public LoggedIn authenticate(LoginRequest request) {
    Optional<User> found = users.findByEmailForUpdate(User.normalizeEmail(request.email()));
    if (found.isEmpty()) {
      passwordEncoder.matches(request.password(), dummyHash);
      throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
    }
    User user = found.get();
    Instant now = clock.instant();
    if (user.isLockedAt(now)) {
      throw BusinessException.retryAfter(
          ErrorCode.AUTH_LOCKED, ceilSeconds(user.lockRemaining(now)));
    }
    if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
      if (user.recordFailure(now)) {
        throw BusinessException.retryAfter(ErrorCode.AUTH_LOCKED, User.LOCK_DURATION.toSeconds());
      }
      throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
    }
    user.recordSuccess();
    return new LoggedIn(user.getId(), user.getRole());
  }

  private static long ceilSeconds(Duration duration) {
    long seconds = duration.toSeconds();
    return duration.toNanosPart() > 0 ? seconds + 1 : seconds;
  }
}
