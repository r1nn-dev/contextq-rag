package com.r1nn.contextq.domain;

import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * {@code created_at}·{@code updated_at} set by the application (db-design §4: no DB DEFAULT).
 *
 * <p>{@code updated_at} changes on every flush of a dirty entity (status transition, terminal
 * update).
 */
@MappedSuperclass
public abstract class BaseTimeEntity {

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
