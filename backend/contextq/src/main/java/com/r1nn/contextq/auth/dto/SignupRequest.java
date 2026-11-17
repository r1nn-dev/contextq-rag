package com.r1nn.contextq.auth.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * {@code POST /api/v1/auth/signup} body (api-spec §1.1, policy §1.1).
 *
 * <p>Email: checked after trim — at most 254 characters, exactly one {@code @}, a {@code .} in the
 * domain (no full RFC check). Password: 8~64 characters with at least one letter and one digit.
 * "Password equals email" is checked by the service against the normalized email.
 */
public record SignupRequest(
    @NotNull(message = EMAIL_MESSAGE) @Pattern(regexp = EMAIL, message = EMAIL_MESSAGE)
        String email,
    @NotNull(message = PASSWORD_MESSAGE) @Pattern(regexp = PASSWORD, message = PASSWORD_MESSAGE)
        String password) {

  /** Optional surrounding spaces, then 1~254 chars: local@domain.with.dot (one @ only). */
  static final String EMAIL = "^\\s*(?=[^\\s]{3,254}\\s*$)[^@\\s]+@[^@\\s.]+(\\.[^@\\s.]+)+\\s*$";

  static final String PASSWORD = "^(?=.*[A-Za-z])(?=.*\\d).{8,64}$";

  public static final String EMAIL_MESSAGE = "올바른 이메일 형식이 아닙니다.";
  public static final String PASSWORD_MESSAGE = "8~64자, 영문·숫자 각 1자 이상이어야 합니다.";
}
