package com.r1nn.contextq.admin.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Request log rows (api-spec §5.5): ended member answers and guest usage logs, newest first.
 *
 * <p>Read-only SQL over app tables (package-structure §1.3). Question text and emails are not
 * selected (policy §9.4).
 */
@Repository
public class AdminLogRepository {

  /**
   * @param actor {@code USER} or {@code GUEST}
   * @param userId null for guests
   */
  public record LogRow(
      Instant at,
      String actor,
      Long userId,
      String requestId,
      String mode,
      String status,
      String statusReason,
      Integer totalMs,
      Integer promptTokens,
      Integer completionTokens) {}

  private final JdbcTemplate jdbc;

  public AdminLogRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * @param statuses terminal statuses to include (level filter)
   * @param before only rows strictly before this instant, or null for the newest page
   */
  public List<LogRow> page(Collection<String> statuses, Instant before, int limit) {
    String in = String.join(", ", Collections.nCopies(statuses.size(), "?"));
    StringBuilder sql =
        new StringBuilder(
            """
            SELECT * FROM (
              SELECT m.updated_at AS at, 'USER' AS actor, m.user_id, m.request_id, c.mode,
                     m.status, m.status_reason, m.total_ms, m.prompt_tokens, m.completion_tokens
              FROM messages m JOIN conversations c ON c.id = m.conversation_id
              WHERE m.role = 'ASSISTANT' AND m.status IN (%s)
              UNION ALL
              SELECT g.created_at, 'GUEST', NULL::bigint, NULL::varchar, 'SINGLE', g.status,
                     NULL::varchar, NULL::int, g.prompt_tokens, g.completion_tokens
              FROM guest_usage_logs g
              WHERE g.status IN (%s)
            ) logs
            """
                .formatted(in, in));
    List<Object> args = new ArrayList<>(statuses);
    args.addAll(statuses);
    if (before != null) {
      sql.append(" WHERE at < ?");
      args.add(Timestamp.from(before));
    }
    sql.append(" ORDER BY at DESC LIMIT ?");
    args.add(limit);
    return jdbc.query(sql.toString(), (rs, n) -> row(rs), args.toArray());
  }

  private static LogRow row(ResultSet rs) throws SQLException {
    return new LogRow(
        rs.getTimestamp("at").toInstant(),
        rs.getString("actor"),
        rs.getObject("user_id", Long.class),
        rs.getString("request_id"),
        rs.getString("mode"),
        rs.getString("status"),
        rs.getString("status_reason"),
        rs.getObject("total_ms", Integer.class),
        rs.getObject("prompt_tokens", Integer.class),
        rs.getObject("completion_tokens", Integer.class));
  }
}
