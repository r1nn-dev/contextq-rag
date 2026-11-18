package com.r1nn.contextq.common.account;

/**
 * Lifts a login lock on behalf of another domain (package-structure §1.3: cross-domain calls go
 * through {@code common/} interfaces). The auth domain owns the account rules and implements it.
 */
public interface AccountUnlocker {

  /**
   * Clears the failure count and the lock so the account is ACTIVE now (policy §10.3 관리자 잠금 해제). An
   * account that is not locked stays as it is.
   *
   * @throws com.r1nn.contextq.common.error.BusinessException {@code USER_NOT_FOUND}
   */
  void unlock(Long userId);
}
