package com.r1nn.contextq.infra.aiserver;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * Body of ai-server {@code GET /internal/v1/index/status} (api-spec §6.6). Times stay as the UTC
 * ISO-8601 strings ai-server sends; the admin API passes them through (§5.1).
 */
public record InternalIndexStatus(List<SourceStatus> sources) {

  public InternalIndexStatus {
    sources = sources == null ? List.of() : List.copyOf(sources);
  }

  /**
   * @param activeRun null when the pointer has no ACTIVE run
   * @param recentRuns newest first, at most 5
   */
  public record SourceStatus(
      String sourceKey,
      String displayName,
      boolean enabled,
      ActiveRun activeRun,
      List<RecentRun> recentRuns) {

    public SourceStatus {
      recentRuns = recentRuns == null ? List.of() : List.copyOf(recentRuns);
    }
  }

  public record ActiveRun(
      long ingestRunId,
      String status,
      String commitSha,
      String chunkStrategy,
      Integer chunkCount,
      Integer prevChunkCount,
      String embeddingModel,
      Long embeddingTokens,
      Double embeddingCostUsd,
      Integer ingestDurationMs,
      String startedAt,
      String completedAt) {}

  /**
   * @param failureStage only for FAILED runs; omitted otherwise
   */
  public record RecentRun(
      long ingestRunId,
      String status,
      String startedAt,
      @JsonInclude(JsonInclude.Include.NON_NULL) String failureStage) {}
}
