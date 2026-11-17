package com.r1nn.contextq.auth.domain;

/** Account status (policy §10.3). LOCKED expires by time, judged at read time. */
public enum UserStatus {
  ACTIVE,
  LOCKED
}
