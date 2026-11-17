package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.auth.service.JwtProvider.AccessClaims;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.JwtProperties;
import com.r1nn.contextq.support.MutableClock;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class JwtProviderTest {

  static final String SECRET = "test-only-jwt-secret-0123456789abcdef-0123456789abcdef";

  private final MutableClock clock = new MutableClock();
  private final JwtProvider provider = new JwtProvider(properties(SECRET), clock);

  @Test
  void issuesDocumentedClaims() {
    String token = provider.issue(12L, UserRole.ROLE_USER);

    JsonNode payload = payload(token);
    assertThat(payload.get("sub").asString()).isEqualTo("12");
    assertThat(payload.get("role").asString()).isEqualTo("ROLE_USER");
    assertThat(payload.get("exp").asLong() - payload.get("iat").asLong()).isEqualTo(1800);
    assertThat(payload.get("jti").asString()).hasSize(36);
    assertThat(provider.expiresInSeconds()).isEqualTo(1800);
    AccessClaims claims = provider.verify(token);
    assertThat(claims.userId()).isEqualTo(12L);
    assertThat(claims.role()).isEqualTo(UserRole.ROLE_USER);
  }

  @Test
  void clockSkewOf30SecondsIsAllowed() {
    String token = provider.issue(1L, UserRole.ROLE_ADMIN);

    clock.advance(Duration.ofMinutes(30).plusSeconds(29));
    assertThat(provider.verify(token).role()).isEqualTo(UserRole.ROLE_ADMIN);

    clock.advance(Duration.ofSeconds(2));
    assertCode(() -> provider.verify(token), ErrorCode.AUTH_TOKEN_EXPIRED);
  }

  @Test
  void tokenSignedWithAnotherKeyIsInvalid() {
    JwtProvider other =
        new JwtProvider(properties("another-test-secret-0123456789abcdef-0123456789"), clock);

    assertCode(
        () -> provider.verify(other.issue(1L, UserRole.ROLE_USER)), ErrorCode.AUTH_TOKEN_INVALID);
  }

  @Test
  void malformedTokenIsInvalid() {
    assertCode(() -> provider.verify("not.a.jwt"), ErrorCode.AUTH_TOKEN_INVALID);
    assertCode(() -> provider.verify(""), ErrorCode.AUTH_TOKEN_INVALID);
  }

  @Test
  void shortSecretFailsFast() {
    assertThatThrownBy(() -> new JwtProvider(properties("too-short"), clock))
        .isInstanceOf(IllegalStateException.class);
  }

  private static void assertCode(Runnable call, ErrorCode code) {
    assertThatThrownBy(call::run)
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.getErrorCode()).isEqualTo(code));
  }

  private static JsonNode payload(String token) {
    String json =
        new String(Base64.getUrlDecoder().decode(token.split("\\.")[1]), StandardCharsets.UTF_8);
    return JsonMapper.builder().build().readTree(json);
  }

  static JwtProperties properties(String secret) {
    return new JwtProperties(
        secret,
        Duration.ofMinutes(30),
        Duration.ofSeconds(30),
        Duration.ofDays(7),
        Duration.ofSeconds(5));
  }
}
