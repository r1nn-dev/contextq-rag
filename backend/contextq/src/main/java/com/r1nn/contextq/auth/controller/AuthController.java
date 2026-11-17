package com.r1nn.contextq.auth.controller;

import com.r1nn.contextq.auth.dto.LoginRequest;
import com.r1nn.contextq.auth.dto.MeResponse;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.dto.SignupResponse;
import com.r1nn.contextq.auth.dto.TokenResponse;
import com.r1nn.contextq.auth.service.JwtProvider;
import com.r1nn.contextq.auth.service.LoginService;
import com.r1nn.contextq.auth.service.LoginService.LoggedIn;
import com.r1nn.contextq.auth.service.SignupService;
import com.r1nn.contextq.auth.service.UserQueryService;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
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

  public AuthController(
      SignupService signupService,
      LoginService loginService,
      JwtProvider jwtProvider,
      UserQueryService userQueryService) {
    this.signupService = signupService;
    this.loginService = loginService;
    this.jwtProvider = jwtProvider;
    this.userQueryService = userQueryService;
  }

  /** api-spec §1.1 — 201 with the new user ID. */
  @PostMapping("/signup")
  public ResponseEntity<ApiResponse<SignupResponse>> signup(
      @Valid @RequestBody SignupRequest request) {
    Long userId = signupService.signup(request);
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok("회원가입이 완료되었습니다.", new SignupResponse(userId)));
  }

  /** api-spec §1.2 — Access Token in the body. */
  @PostMapping("/login")
  public ResponseEntity<ApiResponse<TokenResponse>> login(
      @Valid @RequestBody LoginRequest request) {
    LoggedIn user = loginService.authenticate(request);
    String accessToken = jwtProvider.issue(user.userId(), user.role());
    return ResponseEntity.ok(
        ApiResponse.ok(TokenResponse.bearer(accessToken, jwtProvider.expiresInSeconds())));
  }

  /** api-spec §1.5 — the caller from the Access Token {@code sub}. */
  @GetMapping("/me")
  public ResponseEntity<ApiResponse<MeResponse>> me(Authentication authentication) {
    return ResponseEntity.ok(
        ApiResponse.ok(userQueryService.me(Long.valueOf(authentication.getName()))));
  }
}
