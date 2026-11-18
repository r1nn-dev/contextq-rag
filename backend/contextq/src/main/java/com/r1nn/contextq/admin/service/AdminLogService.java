package com.r1nn.contextq.admin.service;

import com.r1nn.contextq.admin.dto.AdminLogItem;
import com.r1nn.contextq.admin.repository.AdminLogRepository;
import com.r1nn.contextq.common.response.CursorResponse;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Request log of the admin dashboard (api-spec §5.5). */
@Service
public class AdminLogService {

  /** Terminal statuses per level (api-spec §5.5 {@code level}); null level means all of them. */
  static final Map<String, List<String>> STATUSES_BY_LEVEL =
      Map.of(
          "INFO", List.of("COMPLETED"),
          "WARN", List.of("PARTIAL", "NO_CONTEXT"),
          "ERROR", List.of("FAILED"));

  static final List<String> ALL_TERMINAL = List.of("COMPLETED", "PARTIAL", "NO_CONTEXT", "FAILED");

  private final AdminLogRepository logs;

  public AdminLogService(AdminLogRepository logs) {
    this.logs = logs;
  }

  /**
   * @param level {@code INFO}·{@code WARN}·{@code ERROR}, or null for all (validated by the
   *     controller)
   */
  @Transactional(readOnly = true)
  public CursorResponse<AdminLogItem> list(String level, Instant before, int size) {
    List<String> statuses = level == null ? ALL_TERMINAL : STATUSES_BY_LEVEL.get(level);
    List<AdminLogItem> rows =
        logs.page(statuses, before, size + 1).stream().map(AdminLogItem::from).toList();
    boolean hasNext = rows.size() > size;
    List<AdminLogItem> items = hasNext ? rows.subList(0, size) : rows;
    String cursor = hasNext ? items.getLast().at().toString() : null;
    return new CursorResponse<>(items, cursor, hasNext);
  }
}
