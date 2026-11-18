package com.r1nn.contextq.admin.controller;

import com.r1nn.contextq.admin.dto.AdminUsersResponse;
import com.r1nn.contextq.admin.dto.AdminUsersResponse.AdminUserItem;
import com.r1nn.contextq.admin.service.AdminUserService;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Admin user management (api-spec §5.3·§5.4). {@code ROLE_ADMIN} only (SecurityConfig). */
@RestController
@RequestMapping("/api/v1/admin/users")
public class AdminUserController {

  /** Upper bound of {@code size} (api-spec §5.3). */
  static final int MAX_PAGE_SIZE = 50;

  private final AdminUserService users;

  public AdminUserController(AdminUserService users) {
    this.users = users;
  }

  @GetMapping
  public ResponseEntity<ApiResponse<AdminUsersResponse>> list(
      @RequestParam(required = false) @Size(max = 254) String query,
      @RequestParam(required = false) Instant before,
      @RequestParam(defaultValue = "20") @Min(1) @Max(MAX_PAGE_SIZE) int size) {
    return ResponseEntity.ok(ApiResponse.ok(users.list(query, before, size)));
  }

  @PostMapping("/{userId}/unlock")
  public ResponseEntity<ApiResponse<AdminUserItem>> unlock(@PathVariable long userId) {
    return ResponseEntity.ok(ApiResponse.ok(users.unlock(userId)));
  }
}
