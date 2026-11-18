package com.r1nn.contextq.admin.dto;

import com.r1nn.contextq.admin.repository.AdminLogRepository.LogRow;
import java.time.Instant;

/**
 * One request log entry (api-spec §5.5 필드).
 *
 * @param level {@code ERROR} (FAILED), {@code WARN} (PARTIAL·NO_CONTEXT), {@code INFO} (COMPLETED)
 */
public record AdminLogItem(
    Instant at,
    String level,
    String actor,
    Long userId,
    String requestId,
    String mode,
    String status,
    String statusReason,
    Integer totalMs,
    Integer promptTokens,
    Integer completionTokens) {

  public static AdminLogItem from(LogRow row) {
    return new AdminLogItem(
        row.at(),
        levelOf(row.status()),
        row.actor(),
        row.userId(),
        row.requestId(),
        row.mode(),
        row.status(),
        row.statusReason(),
        row.totalMs(),
        row.promptTokens(),
        row.completionTokens());
  }

  static String levelOf(String status) {
    return switch (status) {
      case "FAILED" -> "ERROR";
      case "PARTIAL", "NO_CONTEXT" -> "WARN";
      default -> "INFO";
    };
  }
}
