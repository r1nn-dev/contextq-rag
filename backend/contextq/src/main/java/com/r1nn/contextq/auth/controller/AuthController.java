package com.r1nn.contextq.auth.controller;

import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.dto.SignupResponse;
import com.r1nn.contextq.auth.service.SignupService;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Authentication API (api-spec §1). */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

  private final SignupService signupService;

  public AuthController(SignupService signupService) {
    this.signupService = signupService;
  }

  /** api-spec §1.1 — 201 with the new user ID. */
  @PostMapping("/signup")
  public ResponseEntity<ApiResponse<SignupResponse>> signup(
      @Valid @RequestBody SignupRequest request) {
    Long userId = signupService.signup(request);
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok("회원가입이 완료되었습니다.", new SignupResponse(userId)));
  }
}
