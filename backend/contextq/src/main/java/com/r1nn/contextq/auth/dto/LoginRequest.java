package com.r1nn.contextq.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * {@code POST /api/v1/auth/login} body (api-spec §1.2).
 *
 * <p>Only presence and size are validated; any other mismatch is a credential failure so the
 * response does not tell whether the account exists.
 */
public record LoginRequest(
    @NotBlank(message = "이메일을 입력해주세요.") @Size(max = 300, message = "이메일이 너무 깁니다.") String email,
    @NotBlank(message = "비밀번호를 입력해주세요.") @Size(max = 200, message = "비밀번호가 너무 깁니다.")
        String password) {}
