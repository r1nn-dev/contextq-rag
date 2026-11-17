package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Account creation (api-spec §1.1, policy §1.1). Signup always creates {@code ROLE_USER}. */
@Service
public class SignupService {

  static final String DUPLICATE_EMAIL = "이미 사용 중인 이메일입니다.";
  static final String PASSWORD_EQUALS_EMAIL = "비밀번호는 이메일과 같을 수 없습니다.";

  private final UserRepository users;
  private final PasswordEncoder passwordEncoder;

  public SignupService(UserRepository users, PasswordEncoder passwordEncoder) {
    this.users = users;
    this.passwordEncoder = passwordEncoder;
  }

  /**
   * @return new user ID
   * @throws BusinessException {@code INVALID_REQUEST} — password equals email, or email in use
   *     (also when a concurrent signup wins the UNIQUE constraint)
   */
  @Transactional
  public Long signup(SignupRequest request) {
    String email = User.normalizeEmail(request.email());
    if (request.password().equalsIgnoreCase(email)) {
      throw BusinessException.invalidField("password", PASSWORD_EQUALS_EMAIL);
    }
    if (users.existsByEmail(email)) {
      throw BusinessException.invalidField("email", DUPLICATE_EMAIL);
    }
    try {
      return users
          .saveAndFlush(User.member(email, passwordEncoder.encode(request.password())))
          .getId();
    } catch (DataIntegrityViolationException e) {
      throw BusinessException.invalidField("email", DUPLICATE_EMAIL);
    }
  }
}
