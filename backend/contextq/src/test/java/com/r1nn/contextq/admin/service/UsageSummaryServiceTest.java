package com.r1nn.contextq.admin.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.admin.dto.UsageSummary;
import com.r1nn.contextq.admin.dto.UsageSummary.DailyUsage;
import com.r1nn.contextq.admin.repository.UsageStatsRepository;
import com.r1nn.contextq.support.ChatStreamTestSupport;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

/** KST daily usage: members + guests, date boundary, zero-filled week (api-spec §5.1 응답 규칙). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class UsageSummaryServiceTest {

  /** 2030-03-10 10:00 KST — far from other tests' "now" so their rows never fall in range. */
  static final Instant NOW = Instant.parse("2030-03-10T01:00:00Z");

  @Autowired private UsageStatsRepository stats;
  @Autowired private JdbcTemplate jdbc;

  private UsageSummaryService service;
  private long conversationId;
  private long userId;

  @BeforeEach
  void setUp() {
    jdbc.update(
        "DELETE FROM message_sources WHERE message_id IN"
            + " (SELECT id FROM messages WHERE created_at >= '2030-03-01')");
    jdbc.update("DELETE FROM messages WHERE created_at >= '2030-03-01'");
    jdbc.update("DELETE FROM guest_usage_logs WHERE created_at >= '2030-03-01'");
    service = new UsageSummaryService(stats, Clock.fixed(NOW, ZoneOffset.UTC));
    userId = ChatStreamTestSupport.newUser(jdbc);
    conversationId =
        jdbc.queryForObject(
            "INSERT INTO conversations (user_id, title, mode, source_key, message_count,"
                + " created_at, updated_at) VALUES (?, 't', 'SINGLE', 'langchain_v03', 0, now(),"
                + " now()) RETURNING id",
            Long.class,
            userId);
  }

  @Test
  void sumsMembersAndGuestsPerKstDate() {
    // today (KST 03-10): one member question + answer, two guest questions from one session
    question("2030-03-09T15:00:00Z"); // 03-10 00:00 KST — first instant of today
    answer("2030-03-09T15:00:05Z", 1000, 300);
    guest("aa", "2030-03-10T00:30:00Z", 200, 50);
    guest("aa", "2030-03-10T00:40:00Z", 100, null);
    // yesterday (KST 03-09) — 14:59:59Z is 23:59:59 KST
    question("2030-03-09T14:59:59Z");
    answer("2030-03-09T14:59:59Z", null, null);
    guest("bb", "2030-03-09T03:00:00Z", 10, 5);
    // outside the 7-day window (KST 03-03)
    question("2030-03-03T03:00:00Z");

    UsageSummary summary = service.summary();

    assertThat(summary.today())
        .isEqualTo(new DailyUsage(LocalDate.of(2030, 3, 10), 3, 1300, 350, 1L));
    assertThat(summary.last7Days())
        .extracting(DailyUsage::date)
        .containsExactly(
            LocalDate.of(2030, 3, 4),
            LocalDate.of(2030, 3, 5),
            LocalDate.of(2030, 3, 6),
            LocalDate.of(2030, 3, 7),
            LocalDate.of(2030, 3, 8),
            LocalDate.of(2030, 3, 9),
            LocalDate.of(2030, 3, 10));
    assertThat(summary.last7Days().get(5))
        .isEqualTo(new DailyUsage(LocalDate.of(2030, 3, 9), 2, 10, 5, null));
    assertThat(summary.last7Days().getFirst())
        .isEqualTo(new DailyUsage(LocalDate.of(2030, 3, 4), 0, 0, 0, null));
    assertThat(summary.last7Days().getLast().guestSessions()).isNull();
  }

  @Test
  void emptyWeekIsAllZeros() {
    UsageSummary summary = service.summary();

    assertThat(summary.today().totalMessages()).isZero();
    assertThat(summary.today().guestSessions()).isZero();
    assertThat(summary.last7Days()).hasSize(7).allMatch(d -> d.totalMessages() == 0);
  }

  private void question(String at) {
    jdbc.update(
        "INSERT INTO messages (conversation_id, user_id, role, content, quota_cost, created_at,"
            + " updated_at) VALUES (?, ?, 'USER', 'q', 1, ?, ?)",
        conversationId,
        userId,
        ts(at),
        ts(at));
  }

  private void answer(String at, Integer prompt, Integer completion) {
    jdbc.update(
        "INSERT INTO messages (conversation_id, user_id, role, status, prompt_tokens,"
            + " completion_tokens, created_at, updated_at)"
            + " VALUES (?, ?, 'ASSISTANT', 'COMPLETED', ?, ?, ?, ?)",
        conversationId,
        userId,
        prompt,
        completion,
        ts(at),
        ts(at));
  }

  private void guest(String sid, String at, Integer prompt, Integer completion) {
    jdbc.update(
        "INSERT INTO guest_usage_logs (sid_hash, status, prompt_tokens, completion_tokens,"
            + " created_at) VALUES (?, 'COMPLETED', ?, ?, ?)",
        sid.repeat(32),
        prompt,
        completion,
        ts(at));
  }

  private static Timestamp ts(String instant) {
    return Timestamp.from(Instant.parse(instant));
  }
}
