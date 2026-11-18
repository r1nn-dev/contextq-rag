package com.r1nn.contextq.admin.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Read-only usage aggregation over app tables for the admin dashboard (api-spec §5.1 응답 규칙).
 *
 * <p>Plain SQL instead of the chat repositories keeps the admin domain from importing another
 * domain (package-structure §1.3). Members count by stored messages; guests store only usage logs
 * (policy §6.3 step 5), so both are added up.
 */
@Repository
public class UsageStatsRepository {

  /** Totals of one local day. */
  public record DayTotals(long questions, long promptTokens, long completionTokens) {

    public static final DayTotals ZERO = new DayTotals(0, 0, 0);
  }

  private static final String DAILY_TOTALS =
      """
      SELECT day, SUM(questions) AS questions, SUM(prompt) AS prompt, SUM(completion) AS completion
      FROM (
        SELECT (created_at AT TIME ZONE ?)::date AS day,
               CASE WHEN role = 'USER' THEN 1 ELSE 0 END AS questions,
               CASE WHEN role = 'ASSISTANT' THEN COALESCE(prompt_tokens, 0) ELSE 0 END AS prompt,
               CASE WHEN role = 'ASSISTANT' THEN COALESCE(completion_tokens, 0) ELSE 0 END
                 AS completion
        FROM messages
        WHERE created_at >= ? AND created_at < ?
        UNION ALL
        SELECT (created_at AT TIME ZONE ?)::date, 1, COALESCE(prompt_tokens, 0),
               COALESCE(completion_tokens, 0)
        FROM guest_usage_logs
        WHERE created_at >= ? AND created_at < ?
      ) usage
      GROUP BY day
      """;

  private final JdbcTemplate jdbc;

  public UsageStatsRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * Questions and tokens per local date in {@code [from, to)}; days without records are absent.
   *
   * @param zone zone that defines the date boundary (KST for the dashboard)
   */
  public Map<LocalDate, DayTotals> dailyTotals(Instant from, Instant to, ZoneId zone) {
    Map<LocalDate, DayTotals> totals = new LinkedHashMap<>();
    Timestamp start = Timestamp.from(from);
    Timestamp end = Timestamp.from(to);
    jdbc.query(
        DAILY_TOTALS,
        rs -> {
          totals.put(
              rs.getObject("day", LocalDate.class),
              new DayTotals(
                  rs.getLong("questions"), rs.getLong("prompt"), rs.getLong("completion")));
        },
        zone.getId(),
        start,
        end,
        zone.getId(),
        start,
        end);
    return totals;
  }

  /** Guest sessions that asked at least once in {@code [from, to)} (distinct {@code sid_hash}). */
  public long guestSessions(Instant from, Instant to) {
    Long count =
        jdbc.queryForObject(
            "SELECT COUNT(DISTINCT sid_hash) FROM guest_usage_logs"
                + " WHERE created_at >= ? AND created_at < ?",
            Long.class,
            Timestamp.from(from),
            Timestamp.from(to));
    return count == null ? 0 : count;
  }
}
