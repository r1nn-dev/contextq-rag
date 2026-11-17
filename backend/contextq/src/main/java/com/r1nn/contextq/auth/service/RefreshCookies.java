package com.r1nn.contextq.auth.service;

import java.time.Duration;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

/**
 * {@code devdocs_rt} cookie (api-spec 부록 D.2): {@code HttpOnly; Secure; SameSite=Strict;
 * Path=/api/v1/auth}. The browser sends it only to the auth endpoints.
 */
@Component
public class RefreshCookies {

  public static final String NAME = "devdocs_rt";
  static final String PATH = "/api/v1/auth";

  /** {@code Set-Cookie} value carrying a new token for {@code maxAge}. */
  public String issue(String rawToken, Duration maxAge) {
    return base(rawToken).maxAge(maxAge).build().toString();
  }

  /** {@code Set-Cookie} value that deletes the cookie ({@code Max-Age=0}). */
  public String clear() {
    return base("").maxAge(Duration.ZERO).build().toString();
  }

  private static ResponseCookie.ResponseCookieBuilder base(String value) {
    return ResponseCookie.from(NAME, value)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path(PATH);
  }
}
