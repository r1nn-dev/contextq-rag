package com.r1nn.contextq.chat.domain;

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
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Anonymous session behind the {@code devdocs_sid} cookie (db-design §3.4, policy §1.3).
 *
 * <p>The count changes only through the conditional UPDATEs of the repository (atomic, INV-16); the
 * entity is read-only for the application apart from creation.
 */
@Entity
@Table(name = "guest_sessions")
public class GuestSession {

  /** Questions per session (policy §1.3). */
  public static final int LIMIT = 5;

  /** Absolute lifetime from issue; using the session does not extend it. */
  public static final Duration LIFETIME = Duration.ofHours(24);

  public enum Status {
    ACTIVE,
    EXHAUSTED
  }

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @JdbcTypeCode(SqlTypes.CHAR)
  @Column(name = "sid_hash", nullable = false, length = 64, unique = true, updatable = false)
  private String sidHash;

  @Column(name = "ip_address", nullable = false, length = 45, updatable = false)
  private String ipAddress;

  @Column(name = "used_count", nullable = false)
  private short usedCount;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private Status status;

  @Column(name = "expires_at", nullable = false, updatable = false)
  private Instant expiresAt;

  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected GuestSession() {}

  public static GuestSession open(String sidHash, String ipAddress, Instant now) {
    GuestSession s = new GuestSession();
    s.sidHash = sidHash;
    s.ipAddress = ipAddress;
    s.usedCount = 0;
    s.status = Status.ACTIVE;
    s.expiresAt = now.plus(LIFETIME);
    s.createdAt = now;
    s.updatedAt = now;
    return s;
  }

  public boolean isExpiredAt(Instant now) {
    return !expiresAt.isAfter(now);
  }

  public int remaining() {
    return Math.max(0, LIMIT - usedCount);
  }

  public Long getId() {
    return id;
  }

  public String getSidHash() {
    return sidHash;
  }

  public String getIpAddress() {
    return ipAddress;
  }

  public short getUsedCount() {
    return usedCount;
  }

  public Status getStatus() {
    return status;
  }

  public Instant getExpiresAt() {
    return expiresAt;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
