package com.r1nn.contextq.auth.domain;

/** One role per account (policy §1.1). Signup always creates {@code ROLE_USER}. */
public enum UserRole {
  ROLE_USER,
  ROLE_ADMIN
}
