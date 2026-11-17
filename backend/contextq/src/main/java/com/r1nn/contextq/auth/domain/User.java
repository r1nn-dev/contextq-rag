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
import java.time.Instant;
import java.util.Locale;

/**
 * Account (db-design §3.1, policy §1.1).
 *
 * <p>The email is stored normalized (trimmed, lower case); only the BCrypt hash of the password is
 * kept. Lock state changes are added by the login issue.
 */
@Entity
@Table(name = "users")
public class User extends BaseTimeEntity {

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
}
