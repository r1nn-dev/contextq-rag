package com.r1nn.contextq.auth.domain;

import com.r1nn.contextq.domain.BaseTimeEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;

/**
 * Account (db-design §3.1, policy §1.1).
 *
 * <p>The email is stored normalized (trimmed, lower case); only the BCrypt hash of the password is
 * kept. Failed logins are counted per 15-minute window that starts at the first failure.
 */
@Entity
@Table(name = "users")
public class User extends BaseTimeEntity {

  /** Failures counted inside one window, and the lock length (policy §1.2). */
  public static final int MAX_FAILURES = 5;

  public static final Duration FAILURE_WINDOW = Duration.ofMinutes(15);
  public static final Duration LOCK_DURATION = Duration.ofMinutes(15);

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 254, unique = true)
  private String email;

  @Column(name = "password_hash", nullable = false, length = 72)
  private String passwordHash;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private UserRole role;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private UserStatus status;

  @Column(name = "login_failed_count", nullable = false)
  private short loginFailedCount;

  @Column(name = "locked_at")
  private Instant lockedAt;

  /** Start of the current failure window; null after a success. */
  @Column(name = "login_failed_at")
  private Instant loginFailedAt;

  protected User() {}

  private User(String email, String passwordHash, UserRole role) {
    this.email = normalizeEmail(email);
    this.passwordHash = passwordHash;
    this.role = role;
    this.status = UserStatus.ACTIVE;
    this.loginFailedCount = 0;
  }

  /** Account created by the signup API: always {@code ROLE_USER}. */
  public static User member(String email, String passwordHash) {
    return new User(email, passwordHash, UserRole.ROLE_USER);
  }

  /** Account created by the environment seed only (policy §1.1 관리자 생성). */
  public static User admin(String email, String passwordHash) {
    return new User(email, passwordHash, UserRole.ROLE_ADMIN);
  }

  /** Trim + lower case (policy §1.1 식별자). */
  public static String normalizeEmail(String email) {
    return email == null ? null : email.strip().toLowerCase(Locale.ROOT);
  }

  /** LOCKED and the 15-minute lock has not passed (judged at read time, db-design §3.1). */
  public boolean isLockedAt(Instant now) {
    return status == UserStatus.LOCKED
        && lockedAt != null
        && lockedAt.plus(LOCK_DURATION).isAfter(now);
  }

  /** Time until the lock ends; zero when not locked. */
  public Duration lockRemaining(Instant now) {
    return isLockedAt(now) ? Duration.between(now, lockedAt.plus(LOCK_DURATION)) : Duration.ZERO;
  }

  /**
   * Counts a wrong password. A failure after the window has passed starts a new window (an expired
   * lock is also cleared). The fifth failure inside one window locks the account.
   *
   * @return true when this failure locked the account
   */
  public boolean recordFailure(Instant now) {
    if (loginFailedAt == null || !loginFailedAt.plus(FAILURE_WINDOW).isAfter(now)) {
      loginFailedCount = 1;
      loginFailedAt = now;
      status = UserStatus.ACTIVE;
      lockedAt = null;
    } else {
      loginFailedCount++;
    }
    if (loginFailedCount >= MAX_FAILURES) {
      loginFailedCount = MAX_FAILURES;
      status = UserStatus.LOCKED;
      lockedAt = now;
      return true;
    }
    return false;
  }

  /** Admin unlock (policy §10.3): the same clean state as a successful login. */
  public void unlock() {
    recordSuccess();
  }

  /** Successful login clears the failure state (policy §1.2). */
  public void recordSuccess() {
    loginFailedCount = 0;
    loginFailedAt = null;
    lockedAt = null;
    status = UserStatus.ACTIVE;
  }

  public Long getId() {
    return id;
  }

  public String getEmail() {
    return email;
  }

  public String getPasswordHash() {
    return passwordHash;
  }

  public UserRole getRole() {
    return role;
  }

  public UserStatus getStatus() {
    return status;
  }

  public short getLoginFailedCount() {
    return loginFailedCount;
  }

  public Instant getLockedAt() {
    return lockedAt;
  }

  public Instant getLoginFailedAt() {
    return loginFailedAt;
  }
}
