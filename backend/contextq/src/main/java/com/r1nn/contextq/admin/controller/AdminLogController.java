package com.r1nn.contextq.admin.controller;

import com.r1nn.contextq.admin.dto.AdminLogItem;
import com.r1nn.contextq.admin.service.AdminLogService;
import com.r1nn.contextq.common.response.ApiResponse;
import com.r1nn.contextq.common.response.CursorResponse;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.time.Instant;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Admin request log (api-spec §5.5). {@code ROLE_ADMIN} only (SecurityConfig). */
@RestController
@RequestMapping("/api/v1/admin/logs")
public class AdminLogController {

  /** Upper bound of {@code size} (api-spec §5.5). */
  static final int MAX_PAGE_SIZE = 50;

  private final AdminLogService logs;

  public AdminLogController(AdminLogService logs) {
    this.logs = logs;
  }

  @GetMapping
  public ResponseEntity<ApiResponse<CursorResponse<AdminLogItem>>> list(
      @RequestParam(required = false) @Pattern(regexp = "INFO|WARN|ERROR") String level,
      @RequestParam(required = false) Instant before,
      @RequestParam(defaultValue = "20") @Min(1) @Max(MAX_PAGE_SIZE) int size) {
    return ResponseEntity.ok(ApiResponse.ok(logs.list(level, before, size)));
  }
}
