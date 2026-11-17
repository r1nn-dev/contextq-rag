package com.r1nn.contextq.chat.dto;

import com.r1nn.contextq.infra.aiserver.InternalSources;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * {@code GET /api/v1/sources} body (api-spec §2.1, policy §3.3).
 *
 * @param sources sources satisfying the activity condition (enabled AND ACTIVE run)
 * @param comparePairs catalog pairs with the runtime {@code compareEnabled} flag
 * @param guest guest usage for anonymous callers; null for logged-in users (api-spec §2.1)
 */
public record SourcesResponse(
    List<SourceItem> sources, List<ComparePairItem> comparePairs, GuestUsage guest) {

  /** Same catalog with the caller's guest usage (computed per request, never cached). */
  public SourcesResponse withGuest(GuestUsage usage) {
    return new SourcesResponse(sources, comparePairs, usage);
  }

  /**
   * @param expiresAt session expiry; null without a (valid) cookie
   */
  public record GuestUsage(int limit, int used, int remaining, Instant expiresAt) {}

  /** Keeps only active sources and computes {@code compareEnabled} (policy §3.2). */
  public static SourcesResponse from(InternalSources catalog) {
    Map<String, InternalSources.Source> active =
        catalog.sources().stream()
            .filter(InternalSources.Source::active)
            .collect(Collectors.toMap(InternalSources.Source::sourceKey, Function.identity()));
    List<SourceItem> sources =
        catalog.sources().stream()
            .filter(InternalSources.Source::active)
            .map(SourceItem::from)
            .toList();
    List<ComparePairItem> pairs =
        catalog.comparePairs().stream()
            .map(
                p ->
                    new ComparePairItem(
                        active.containsKey(p.sourceKeyA()) && active.containsKey(p.sourceKeyB()),
                        p.sourceKeyA(),
                        p.sourceKeyB()))
            .toList();
    return new SourcesResponse(sources, pairs, null);
  }

  public record SourceItem(
      String sourceKey,
      String framework,
      String versionLabel,
      String displayName,
      boolean enabled,
      ActiveRun activeRun) {

    static SourceItem from(InternalSources.Source s) {
      return new SourceItem(
          s.sourceKey(),
          s.framework(),
          s.versionLabel(),
          s.displayName(),
          s.enabled(),
          new ActiveRun(s.commitSha(), s.ingestedAt(), s.chunkCount()));
    }
  }

  /**
   * @param ingestedAt YYYY-MM-DD (UTC completion date)
   */
  public record ActiveRun(String commitSha, String ingestedAt, Integer chunkCount) {}

  public record ComparePairItem(boolean compareEnabled, String sourceKeyA, String sourceKeyB) {}
}
