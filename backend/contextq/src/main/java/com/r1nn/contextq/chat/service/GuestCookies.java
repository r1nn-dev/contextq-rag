package com.r1nn.contextq.chat.service;

import java.time.Duration;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

/**
 * {@code devdocs_sid} cookie (api-spec 부록 D.3): {@code HttpOnly; Secure; SameSite=Strict;
 * Path=/api}.
 */
@Component
public class GuestCookies {

  public static final String NAME = "devdocs_sid";

  /** {@code Set-Cookie} value for a newly issued session. */
  public String issue(String rawSid, Duration maxAge) {
    return ResponseCookie.from(NAME, rawSid)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path("/api")
        .maxAge(maxAge)
        .build()
        .toString();
  }
}
