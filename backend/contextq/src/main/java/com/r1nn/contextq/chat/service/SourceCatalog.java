package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.dto.SourcesResponse;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.infra.aiserver.AiServerSourcesClient;
import com.r1nn.contextq.infra.aiserver.AiServerUnavailableException;
import com.r1nn.contextq.infra.aiserver.InternalSources;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Source catalog cached for 60 seconds (policy §2.1 메타 API 캐시, api-spec 부록 A).
 *
 * <p>backend never reads the ai schema; this is the only way it learns sources and ACTIVE runs.
 * Concurrent expiry triggers one internal call. When the refresh fails the previous snapshot is
 * kept (retried after {@link #RETRY_AFTER_FAILURE}); without any snapshot the caller gets {@code
 * AI_UNAVAILABLE}.
 */
@Service
public class SourceCatalog {

  static final Duration RETRY_AFTER_FAILURE = Duration.ofSeconds(10);

  private static final Logger log = LoggerFactory.getLogger(SourceCatalog.class);

  private final AiServerSourcesClient client;
  private final Clock clock;
  private final Duration ttl;
  private final Object refreshLock = new Object();
  private volatile Snapshot snapshot;

  public SourceCatalog(AiServerSourcesClient client, Clock clock, AiServerProperties properties) {
    this.client = client;
    this.clock = clock;
    this.ttl = properties.sourcesCacheTtl();
  }

  /**
   * Current catalog, refreshed when expired.
   *
   * @throws BusinessException {@code AI_UNAVAILABLE} when ai-server fails and nothing is cached
   */
  public InternalSources current() {
    Snapshot current = snapshot;
    if (current != null && current.freshAt(clock.instant())) {
      return current.data();
    }
    synchronized (refreshLock) {
      current = snapshot;
      Instant now = clock.instant();
      if (current != null && current.freshAt(now)) {
        return current.data();
      }
      try {
        InternalSources fetched = client.fetch();
        snapshot = new Snapshot(fetched, now.plus(ttl));
        return fetched;
      } catch (AiServerUnavailableException e) {
        if (current == null) {
          log.warn("sources_fetch_failed cached=false", e);
          throw new BusinessException(ErrorCode.AI_UNAVAILABLE);
        }
        log.warn("sources_fetch_failed cached=true — serving previous snapshot", e);
        snapshot = new Snapshot(current.data(), now.plus(RETRY_AFTER_FAILURE));
        return current.data();
      }
    }
  }

  /**
   * Public source list (api-spec §2.1).
   *
   * @throws BusinessException {@code INDEX_NOT_ACTIVE} when enabled sources exist but none has an
   *     ACTIVE run; {@code AI_UNAVAILABLE} when ai-server fails and nothing is cached
   */
  public SourcesResponse publicSources() {
    InternalSources catalog = current();
    SourcesResponse response = SourcesResponse.from(catalog);
    boolean anyEnabled = catalog.sources().stream().anyMatch(InternalSources.Source::enabled);
    if (response.sources().isEmpty() && anyEnabled) {
      log.error("index_not_active — enabled sources without an ACTIVE run");
      throw new BusinessException(ErrorCode.INDEX_NOT_ACTIVE);
    }
    return response;
  }

  /**
   * Pre-check of the version a question targets (api-spec §3.1 스트림 전 오류, policy §3.2).
   *
   * @param followUp true for an existing conversation: a source that disappeared from the catalog
   *     is reported as {@code SOURCE_UNAVAILABLE} (the conversation became read-only, policy §2.3)
   * @throws BusinessException {@code SOURCE_NOT_FOUND}, {@code SOURCE_UNAVAILABLE} (disabled) or
   *     {@code INDEX_NOT_ACTIVE} (no ACTIVE run)
   */
  public InternalSources.Source requireAskable(String sourceKey, boolean followUp) {
    InternalSources.Source source =
        current().sources().stream()
            .filter(s -> s.sourceKey().equals(sourceKey))
            .findFirst()
            .orElseThrow(
                () ->
                    new BusinessException(
                        followUp ? ErrorCode.SOURCE_UNAVAILABLE : ErrorCode.SOURCE_NOT_FOUND));
    if (!source.enabled()) {
      throw new BusinessException(ErrorCode.SOURCE_UNAVAILABLE);
    }
    if (source.activeRunId() == null) {
      throw new BusinessException(ErrorCode.INDEX_NOT_ACTIVE);
    }
    return source;
  }

  /** Drops the cache so the next call refetches (index activation, tests). */
  public void invalidate() {
    snapshot = null;
  }

  private record Snapshot(InternalSources data, Instant expiresAt) {
    boolean freshAt(Instant now) {
      return now.isBefore(expiresAt);
    }
  }
}
