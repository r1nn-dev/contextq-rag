package com.r1nn.contextq.admin.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Read-only user rows for the admin user list (api-spec §5.3). Plain SQL keeps the admin domain
 * from importing the auth repositories (package-structure §1.3); writes go through {@code
 * AccountUnlocker}. Password hashes and tokens are never selected.
 */
@Repository
public class AdminUserRepository {

  /**
   * @param lockedAt stored lock time; whether it still holds is judged by the caller (policy §1.2)
   * @param todayQuotaUsed sum of today's USER {@code quota_cost}
   */
  public record UserRow(
      long userId,
      String email,
      String role,
      String status,
      Instant lockedAt,
      Instant createdAt,
      long totalQuestions,
      long todayQuotaUsed) {}

  /** Account counts regardless of the search. */
  public record Counts(long total, long admins, long members, long locked) {}

  private static final String SELECT =
      """
      SELECT u.id, u.email, u.role, u.status, u.locked_at, u.created_at,
             (SELECT COUNT(*) FROM messages m WHERE m.user_id = u.id AND m.role = 'USER')
               AS total_questions,
             (SELECT COALESCE(SUM(m.quota_cost), 0) FROM messages m
               WHERE m.user_id = u.id AND m.role = 'USER' AND m.created_at >= ?)
               AS today_used
      FROM users u
      """;

  private final JdbcTemplate jdbc;

  public AdminUserRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * Newest accounts first ({@code created_at DESC, id DESC}).
   *
   * @param emailPart lower-case substring of the email, or null for all
   * @param before only accounts created before this instant, or null for the first page
   * @param todayStart start of today (KST) for {@code todayQuotaUsed}
   */
  public List<UserRow> page(String emailPart, Instant before, int limit, Instant todayStart) {
    StringBuilder sql = new StringBuilder(SELECT).append(" WHERE 1 = 1");
    List<Object> args = new ArrayList<>();
    args.add(Timestamp.from(todayStart));
    if (emailPart != null) {
      sql.append(" AND u.email LIKE ? ESCAPE '\\'");
      args.add("%" + escapeLike(emailPart) + "%");
    }
    if (before != null) {
      sql.append(" AND u.created_at < ?");
      args.add(Timestamp.from(before));
    }
    sql.append(" ORDER BY u.created_at DESC, u.id DESC LIMIT ?");
    args.add(limit);
    return jdbc.query(sql.toString(), (rs, n) -> row(rs), args.toArray());
  }

  public Optional<UserRow> find(long userId, Instant todayStart) {
    return jdbc
        .query(SELECT + " WHERE u.id = ?", (rs, n) -> row(rs), Timestamp.from(todayStart), userId)
        .stream()
        .findFirst();
  }

  /**
   * @param lockedSince locks taken after this instant still hold (now − 15 min)
   */
  public Counts counts(Instant lockedSince) {
    return jdbc.queryForObject(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE role = 'ROLE_ADMIN') AS admins,
               COUNT(*) FILTER (WHERE role = 'ROLE_USER') AS members,
               COUNT(*) FILTER (WHERE status = 'LOCKED' AND locked_at > ?) AS locked
        FROM users
        """,
        (rs, n) ->
            new Counts(
                rs.getLong("total"),
                rs.getLong("admins"),
                rs.getLong("members"),
                rs.getLong("locked")),
        Timestamp.from(lockedSince));
  }

  private static UserRow row(ResultSet rs) throws SQLException {
    Timestamp lockedAt = rs.getTimestamp("locked_at");
    return new UserRow(
        rs.getLong("id"),
        rs.getString("email"),
        rs.getString("role"),
        rs.getString("status"),
        lockedAt == null ? null : lockedAt.toInstant(),
        rs.getTimestamp("created_at").toInstant(),
        rs.getLong("total_questions"),
        rs.getLong("today_used"));
  }

  /** LIKE wildcards in the search text are matched literally. */
  static String escapeLike(String text) {
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
  }
}
