package com.r1nn.contextq.admin.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.LocalDate;
import java.util.List;

/**
 * {@code usageSummary} of {@code GET /api/v1/admin/index/status} (api-spec §5.1 응답 규칙).
 *
 * @param today today's totals with {@code guestSessions}
 * @param last7Days the last 7 days including today, oldest first, zero-filled
 */
public record UsageSummary(DailyUsage today, List<DailyUsage> last7Days) {

  /**
   * Totals of one KST date.
   *
   * @param totalMessages member questions + guest usage logs
   * @param guestSessions only on {@code today}; omitted from {@code last7Days}
   */
  public record DailyUsage(
      LocalDate date,
      long totalMessages,
      long promptTokens,
      long completionTokens,
      @JsonInclude(JsonInclude.Include.NON_NULL) Long guestSessions) {}
}
