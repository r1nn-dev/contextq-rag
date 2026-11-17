package com.r1nn.contextq.auth.controller;

import com.r1nn.contextq.auth.dto.LoginRequest;
import com.r1nn.contextq.auth.dto.MeResponse;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.dto.SignupResponse;
import com.r1nn.contextq.auth.dto.TokenResponse;
import com.r1nn.contextq.auth.service.JwtProvider;
import com.r1nn.contextq.auth.service.LoginService;
import com.r1nn.contextq.auth.service.LoginService.LoggedIn;
import com.r1nn.contextq.auth.service.RefreshCookies;
import com.r1nn.contextq.auth.service.RefreshTokenService;
import com.r1nn.contextq.auth.service.RefreshTokenService.Issued;
import com.r1nn.contextq.auth.service.RefreshTokenService.Rotated;
import com.r1nn.contextq.auth.service.SignupService;
import com.r1nn.contextq.auth.service.UserQueryService;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Authentication API (api-spec §1). */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

  private final SignupService signupService;
  private final LoginService loginService;
  private final JwtProvider jwtProvider;
  private final UserQueryService userQueryService;
  private final RefreshTokenService refreshTokenService;
  private final RefreshCookies refreshCookies;

  public AuthController(
      SignupService signupService,
      LoginService loginService,
      JwtProvider jwtProvider,
      UserQueryService userQueryService,
      RefreshTokenService refreshTokenService,
      RefreshCookies refreshCookies) {
    this.signupService = signupService;
    this.loginService = loginService;
    this.jwtProvider = jwtProvider;
    this.userQueryService = userQueryService;
    this.refreshTokenService = refreshTokenService;
    this.refreshCookies = refreshCookies;
  }

  /** api-spec §1.1 — 201 with the new user ID. */
  @PostMapping("/signup")
  public ResponseEntity<ApiResponse<SignupResponse>> signup(
      @Valid @RequestBody SignupRequest request) {
    Long userId = signupService.signup(request);
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok("회원가입이 완료되었습니다.", new SignupResponse(userId)));
  }

  /** api-spec §1.2 — Access Token in the body, refresh token in the {@code devdocs_rt} cookie. */
  @PostMapping("/login")
  public ResponseEntity<ApiResponse<TokenResponse>> login(
      @Valid @RequestBody LoginRequest request) {
    LoggedIn user = loginService.authenticate(request);
    Issued refresh = refreshTokenService.startFamily(user.userId());
    return tokens(user.userId(), user, refresh);
  }

  /** api-spec §1.3 — rotation; errors carry their own {@code Set-Cookie} when needed. */
  @PostMapping("/refresh")
  public ResponseEntity<ApiResponse<TokenResponse>> refresh(
      @CookieValue(name = RefreshCookies.NAME, required = false) String refreshToken) {
    Rotated rotated = refreshTokenService.rotate(refreshToken);
    String accessToken = jwtProvider.issue(rotated.userId(), rotated.role());
    return ResponseEntity.ok()
        .header(
            HttpHeaders.SET_COOKIE,
            refreshCookies.issue(rotated.next().rawToken(), rotated.next().maxAge()))
        .body(ApiResponse.ok(TokenResponse.bearer(accessToken, jwtProvider.expiresInSeconds())));
  }

  /** api-spec §1.4 — idempotent; always clears the cookie. */
  @PostMapping("/logout")
  public ResponseEntity<ApiResponse<Void>> logout(
      @CookieValue(name = RefreshCookies.NAME, required = false) String refreshToken) {
    refreshTokenService.logout(refreshToken);
    return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, refreshCookies.clear())
        .body(ApiResponse.ok("로그아웃되었습니다.", null));
  }

  private ResponseEntity<ApiResponse<TokenResponse>> tokens(
      Long userId, LoggedIn user, Issued refresh) {
    String accessToken = jwtProvider.issue(userId, user.role());
    return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, refreshCookies.issue(refresh.rawToken(), refresh.maxAge()))
        .body(ApiResponse.ok(TokenResponse.bearer(accessToken, jwtProvider.expiresInSeconds())));
  }

  /** api-spec §1.5 — the caller from the Access Token {@code sub}. */
  @GetMapping("/me")
  public ResponseEntity<ApiResponse<MeResponse>> me(Authentication authentication) {
    return ResponseEntity.ok(
        ApiResponse.ok(userQueryService.me(Long.valueOf(authentication.getName()))));
  }
}
