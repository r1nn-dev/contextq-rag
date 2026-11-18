package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.account.AccountUnlocker;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Admin unlock of a login lock (policy §1.2·§10.3, api-spec §5.4). */
@Service
public class AccountUnlockService implements AccountUnlocker {

  private static final Logger log = LoggerFactory.getLogger(AccountUnlockService.class);

  private final UserRepository users;

  public AccountUnlockService(UserRepository users) {
    this.users = users;
  }

  /** Takes the user row lock, the same one a login failure takes, so the two are serialized. */
  @Override
  @Transactional
  public void unlock(Long userId) {
    User user =
        users
            .findByIdForUpdate(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    user.unlock();
    log.info("account_unlocked_by_admin userId={}", userId);
  }
}
