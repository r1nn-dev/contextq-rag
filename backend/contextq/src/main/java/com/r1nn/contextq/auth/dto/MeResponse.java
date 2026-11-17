package com.r1nn.contextq.auth.dto;

import com.r1nn.contextq.auth.domain.User;
import java.time.Instant;

/** {@code GET /api/v1/auth/me} data (api-spec §1.5). */
public record MeResponse(Long userId, String email, String role, Instant createdAt) {

  public static MeResponse from(User user) {
    return new MeResponse(
        user.getId(), user.getEmail(), user.getRole().name(), user.getCreatedAt());
  }
}
