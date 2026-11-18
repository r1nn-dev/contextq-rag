package com.r1nn.contextq.admin.service;

import com.r1nn.contextq.admin.dto.UsageSummary;
import com.r1nn.contextq.admin.dto.UsageSummary.DailyUsage;
import com.r1nn.contextq.admin.repository.UsageStatsRepository;
import com.r1nn.contextq.admin.repository.UsageStatsRepository.DayTotals;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Daily usage of the admin dashboard in KST dates (api-spec §5.1 응답 규칙, policy §8.2). */
@Service
public class UsageSummaryService {

  /** Same date boundary as the daily quota (policy §8.1 KST 00:00). */
  static final ZoneId USAGE_ZONE = ZoneId.of("Asia/Seoul");

  /** Days in {@code last7Days}, today included. */
  static final int DAYS = 7;

  private final UsageStatsRepository stats;
  private final Clock clock;

  public UsageSummaryService(UsageStatsRepository stats, Clock clock) {
    this.stats = stats;
    this.clock = clock;
  }

  /** Today (with guest sessions) and the last 7 days, oldest first, days without records as 0. */
  @Transactional(readOnly = true)
  public UsageSummary summary() {
    LocalDate today = LocalDate.now(clock.withZone(USAGE_ZONE));
    LocalDate first = today.minusDays(DAYS - 1);
    Instant from = startOf(first);
    Instant to = startOf(today.plusDays(1));
    Map<LocalDate, DayTotals> totals = stats.dailyTotals(from, to, USAGE_ZONE);

    List<DailyUsage> days = new ArrayList<>();
    for (LocalDate day = first; !day.isAfter(today); day = day.plusDays(1)) {
      days.add(usage(day, totals.getOrDefault(day, DayTotals.ZERO), null));
    }
    long guestSessions = stats.guestSessions(startOf(today), to);
    DailyUsage todayUsage = usage(today, totals.getOrDefault(today, DayTotals.ZERO), guestSessions);
    return new UsageSummary(todayUsage, days);
  }

  private static DailyUsage usage(LocalDate day, DayTotals t, Long guestSessions) {
    return new DailyUsage(
        day, t.questions(), t.promptTokens(), t.completionTokens(), guestSessions);
  }

  private static Instant startOf(LocalDate day) {
    return day.atStartOfDay(USAGE_ZONE).toInstant();
  }
}
