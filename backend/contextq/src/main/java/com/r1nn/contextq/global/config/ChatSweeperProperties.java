package com.r1nn.contextq.global.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Stuck answer sweeper (policy §2.1, db-design §5).
 *
 * @param interval delay between runs (60 s)
 * @param staleAfter age of the last update after which STREAMING·PENDING is stuck (150 s)
 */
@ConfigurationProperties("chat.sweeper")
public record ChatSweeperProperties(
    @DefaultValue("60s") Duration interval, @DefaultValue("150s") Duration staleAfter) {}
