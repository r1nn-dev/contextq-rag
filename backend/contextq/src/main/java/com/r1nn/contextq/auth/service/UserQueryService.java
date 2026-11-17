package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.dto.MeResponse;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Read side of the account (api-spec §1.5). */
@Service
public class UserQueryService {

  private final UserRepository users;

  public UserQueryService(UserRepository users) {
    this.users = users;
  }

  /**
   * @throws BusinessException {@code AUTH_TOKEN_INVALID} when the token names no existing user
   */
  @Transactional(readOnly = true)
  public MeResponse me(Long userId) {
    return users
        .findById(userId)
        .map(MeResponse::from)
        .orElseThrow(() -> new BusinessException(ErrorCode.AUTH_TOKEN_INVALID));
  }
}
