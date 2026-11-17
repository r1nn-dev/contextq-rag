package com.r1nn.contextq.auth.dto;

/**
 * Access Token in the login·refresh response body (api-spec §1.2·§1.3).
 *
 * @param expiresIn lifetime in seconds (1800)
 */
public record TokenResponse(String accessToken, String tokenType, long expiresIn) {

  public static TokenResponse bearer(String accessToken, long expiresIn) {
    return new TokenResponse(accessToken, "Bearer", expiresIn);
  }
}
