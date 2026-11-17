package com.r1nn.contextq.global.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Token settings (policy §1.2·§2.1, api-spec 부록 D).
 *
 * @param secret HS256 signing key ({@code JWT_SECRET}), at least 32 bytes
 * @param accessTokenTtl Access Token lifetime (30 min)
 * @param clockSkew allowed clock difference for {@code exp}/{@code iat} (30 s)
 * @param refreshFamilyTtl absolute lifetime of a refresh family from login (7 days)
 * @param refreshReuseGrace window in which a just-rotated token is a race, not reuse (5 s)
 */
@ConfigurationProperties("jwt")
public record JwtProperties(
    String secret,
    @DefaultValue("30m") Duration accessTokenTtl,
    @DefaultValue("30s") Duration clockSkew,
    @DefaultValue("7d") Duration refreshFamilyTtl,
    @DefaultValue("5s") Duration refreshReuseGrace) {}
