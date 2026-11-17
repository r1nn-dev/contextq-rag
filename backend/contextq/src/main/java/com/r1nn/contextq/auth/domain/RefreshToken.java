package com.r1nn.contextq.auth.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Rotating refresh token (db-design §3.3). Only the SHA-256 hex is stored.
 *
 * <p>{@code updatedAt} is the status change time and is set explicitly so the 5-second reuse grace
 * is measured from the rotation itself.
 */
@Entity
@Table(name = "refresh_tokens")
public class RefreshToken {

  public enum Status {
    ACTIVE,
    USED,
    REVOKED
  }

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "family_id", nullable = false, updatable = false)
  private TokenFamily family;

  @JdbcTypeCode(SqlTypes.CHAR)
  @Column(name = "token_hash", nullable = false, length = 64, unique = true, updatable = false)
  private String tokenHash;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private Status status;

  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected RefreshToken() {}

  public static RefreshToken issue(TokenFamily family, String tokenHash, Instant now) {
    RefreshToken token = new RefreshToken();
    token.family = family;
    token.tokenHash = tokenHash;
    token.status = Status.ACTIVE;
    token.createdAt = now;
    token.updatedAt = now;
    return token;
  }

  /** ACTIVE → USED on rotation (policy §10.3). */
  public void markUsed(Instant now) {
    if (status != Status.ACTIVE) {
      throw new IllegalStateException("only an ACTIVE token can be rotated");
    }
    status = Status.USED;
    updatedAt = now;
  }

  /** ACTIVE·USED → REVOKED (logout, reuse detection, cap cleanup). */
  public void revoke(Instant now) {
    if (status != Status.REVOKED) {
      status = Status.REVOKED;
      updatedAt = now;
    }
  }

  /** A USED token re-sent within {@code grace} of its rotation is a multi-tab race. */
  public boolean usedWithin(java.time.Duration grace, Instant now) {
    return status == Status.USED && updatedAt.plus(grace).isAfter(now);
  }

  public Long getId() {
    return id;
  }

  public TokenFamily getFamily() {
    return family;
  }

  public String getTokenHash() {
    return tokenHash;
  }

  public Status getStatus() {
    return status;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
