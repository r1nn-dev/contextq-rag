package com.r1nn.contextq.global.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * backend usage limits (policy §8.1, api-spec §0.7). Admins get the same limits.
 *
 * @param perMinute questions per minute per user (token bucket)
 * @param daily questions per KST day per user; compare mode counts 2
 * @param concurrentUser open streams per user
 * @param concurrentGuest open streams per guest session
 */
@ConfigurationProperties("chat.quota")
public record QuotaProperties(
    @DefaultValue("10") int perMinute,
    @DefaultValue("100") int daily,
    @DefaultValue("2") int concurrentUser,
    @DefaultValue("1") int concurrentGuest) {}
