package com.r1nn.contextq.admin.service;

import com.r1nn.contextq.admin.dto.AdminUsersResponse;
import com.r1nn.contextq.admin.dto.AdminUsersResponse.AdminUserItem;
import com.r1nn.contextq.admin.dto.AdminUsersResponse.Summary;
import com.r1nn.contextq.admin.repository.AdminUserRepository;
import com.r1nn.contextq.admin.repository.AdminUserRepository.Counts;
import com.r1nn.contextq.admin.repository.AdminUserRepository.UserRow;
import com.r1nn.contextq.common.account.AccountUnlocker;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.QuotaProperties;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Admin user list and unlock (api-spec §5.3·§5.4). */
@Service
public class AdminUserService {

  /** Lock length of policy §1.2; the lock is judged at read time. */
  static final Duration LOCK_DURATION = Duration.ofMinutes(15);

  /** Daily quota boundary (policy §8.1 KST 00:00). */
  static final ZoneId QUOTA_ZONE = ZoneId.of("Asia/Seoul");

  private final AdminUserRepository users;
  private final AccountUnlocker unlocker;
  private final QuotaProperties quota;
  private final Clock clock;

  public AdminUserService(
      AdminUserRepository users, AccountUnlocker unlocker, QuotaProperties quota, Clock clock) {
    this.users = users;
    this.unlocker = unlocker;
    this.quota = quota;
    this.clock = clock;
  }

  /**
   * @param query email part (trimmed, case-insensitive), blank for all
   * @param before cursor ({@code createdAt} of the previous page's last item)
   */
  @Transactional(readOnly = true)
  public AdminUsersResponse list(String query, Instant before, int size) {
    Instant now = clock.instant();
    String emailPart =
        query == null || query.isBlank() ? null : query.strip().toLowerCase(Locale.ROOT);
    List<UserRow> rows = users.page(emailPart, before, size + 1, todayStart(now));
    boolean hasNext = rows.size() > size;
    List<AdminUserItem> items = rows.stream().limit(size).map(row -> item(row, now)).toList();
    String cursor = hasNext ? items.getLast().createdAt().toString() : null;
    Counts c = users.counts(now.minus(LOCK_DURATION));
    return new AdminUsersResponse(
        items, cursor, hasNext, new Summary(c.total(), c.admins(), c.members(), c.locked()));
  }

  /**
   * Lifts the login lock through the auth domain, then reads the account back.
   *
   * <p>Deliberately not one transaction: the unlock commits in its own (JPA) transaction first, so
   * the plain-SQL read that follows sees it. Inside one transaction the JDBC read would run before
   * Hibernate flushes the change and still report LOCKED.
   *
   * @throws BusinessException {@code USER_NOT_FOUND}
   */
  public AdminUserItem unlock(long userId) {
    unlocker.unlock(userId);
    Instant now = clock.instant();
    return users
        .find(userId, todayStart(now))
        .map(row -> item(row, now))
        .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
  }

  private AdminUserItem item(UserRow row, Instant now) {
    Instant until = row.lockedAt() == null ? null : row.lockedAt().plus(LOCK_DURATION);
    boolean locked = "LOCKED".equals(row.status()) && until != null && until.isAfter(now);
    return new AdminUserItem(
        row.userId(),
        row.email(),
        row.role(),
        locked ? "LOCKED" : "ACTIVE",
        locked ? until : null,
        row.createdAt(),
        row.totalQuestions(),
        row.todayQuotaUsed(),
        quota.daily());
  }

  private static Instant todayStart(Instant now) {
    return LocalDate.ofInstant(now, QUOTA_ZONE).atStartOfDay(QUOTA_ZONE).toInstant();
  }
}
