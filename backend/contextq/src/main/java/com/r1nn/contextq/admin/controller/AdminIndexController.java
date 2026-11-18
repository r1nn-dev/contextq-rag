package com.r1nn.contextq.admin.controller;

import com.r1nn.contextq.admin.dto.IndexStatusResponse;
import com.r1nn.contextq.admin.service.IndexStatusService;
import com.r1nn.contextq.common.response.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Admin index dashboard (api-spec §5.1). {@code /api/v1/admin/**} requires {@code ROLE_ADMIN}
 * (SecurityConfig): no token → 401, a user token → 403 {@code FORBIDDEN}.
 */
@RestController
@RequestMapping("/api/v1/admin/index")
public class AdminIndexController {

  private final IndexStatusService indexStatus;

  public AdminIndexController(IndexStatusService indexStatus) {
    this.indexStatus = indexStatus;
  }

  @GetMapping("/status")
  public ResponseEntity<ApiResponse<IndexStatusResponse>> status() {
    return ResponseEntity.ok(ApiResponse.ok(indexStatus.status()));
  }
}
