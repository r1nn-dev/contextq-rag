package com.r1nn.contextq.global.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * backend → ai-server connection settings (policy §2.1, api-spec 부록 A, ADR-012).
 *
 * @param baseUrl internal URL ({@code AI_SERVER_INTERNAL_URL})
 * @param internalToken shared token sent as {@code X-Internal-Token} ({@code INTERNAL_TOKEN})
 * @param connectTimeout TCP connect limit; exceeding it means {@code AI_UNAVAILABLE}
 * @param requestTimeout limit for plain JSON calls such as the source list
 * @param firstEventTimeout limit until the first SSE event ({@code meta}) arrives
 * @param idleTimeout maximum gap between SSE events including heartbeats
 * @param sourcesCacheTtl source list cache lifetime ({@code GET /api/v1/sources})
 */
@ConfigurationProperties("ai-server")
public record AiServerProperties(
    String baseUrl,
    String internalToken,
    @DefaultValue("3s") Duration connectTimeout,
    @DefaultValue("5s") Duration requestTimeout,
    @DefaultValue("15s") Duration firstEventTimeout,
    @DefaultValue("30s") Duration idleTimeout,
    @DefaultValue("60s") Duration sourcesCacheTtl) {}
