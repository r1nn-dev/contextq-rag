package com.r1nn.contextq.global.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * One-time admin seed (policy §1.1 관리자 생성).
 *
 * @param email {@code ADMIN_EMAIL}; empty disables the seed
 * @param passwordBcrypt {@code ADMIN_PASSWORD_BCRYPT} — a BCrypt hash, never the plain password
 */
@ConfigurationProperties("app.admin")
public record AdminSeedProperties(String email, String passwordBcrypt) {}
