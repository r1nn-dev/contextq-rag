package com.r1nn.contextq.admin.dto;

import java.time.Instant;
import java.util.List;

/**
 * {@code GET /api/v1/admin/users} body (api-spec §5.3): a cursor page plus account counts.
 *
 * @param cursor {@code createdAt} of the last item for the next {@code before}; null on the last
 *     page
 */
public record AdminUsersResponse(
    List<AdminUserItem> items, String cursor, boolean hasNext, Summary summary) {

  public AdminUsersResponse {
    items = List.copyOf(items);
  }

  /**
   * One account (api-spec §5.3 필드).
   *
   * @param status {@code LOCKED} while the 15-minute lock holds, otherwise {@code ACTIVE}
   * @param lockedUntil end of the lock; null when {@code ACTIVE}
   */
  public record AdminUserItem(
      long userId,
      String email,
      String role,
      String status,
      Instant lockedUntil,
      Instant createdAt,
      long totalQuestions,
      long todayQuotaUsed,
      int dailyQuota) {}

  /** Counts over all accounts, independent of the search. */
  public record Summary(long totalUsers, long admins, long members, long locked) {}
}
