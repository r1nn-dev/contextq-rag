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

/**
 * One login session (db-design §3.2). Absolute expiry: rotations never extend it (policy §1.2).
 * Expiry is judged by time, not stored as a status (policy §10).
 */
@Entity
@Table(name = "token_families")
public class TokenFamily extends BaseTimeEntity {

  public enum Status {
    ACTIVE,
    REVOKED
  }

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "user_id", nullable = false, updatable = false)
  private Long userId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private Status status;

  @Column(name = "expires_at", nullable = false, updatable = false)
  private Instant expiresAt;

  protected TokenFamily() {}

  public static TokenFamily start(Long userId, Instant loginAt, Duration lifetime) {
    TokenFamily family = new TokenFamily();
    family.userId = userId;
    family.status = Status.ACTIVE;
    family.expiresAt = loginAt.plus(lifetime);
    return family;
  }

  public boolean isExpiredAt(Instant now) {
    return !expiresAt.isAfter(now);
  }

  public boolean isRevoked() {
    return status == Status.REVOKED;
  }

  public void revoke() {
    status = Status.REVOKED;
  }

  public Duration remainingAt(Instant now) {
    return isExpiredAt(now) ? Duration.ZERO : Duration.between(now, expiresAt);
  }

  public Long getId() {
    return id;
  }

  public Long getUserId() {
    return userId;
  }

  public Status getStatus() {
    return status;
  }

  public Instant getExpiresAt() {
    return expiresAt;
  }
}
