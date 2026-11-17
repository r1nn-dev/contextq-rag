package com.r1nn.contextq.infra.aiserver;

import java.util.List;

/**
 * Body of ai-server {@code GET /internal/v1/sources} (api-spec §6.3).
 *
 * @param sources every catalog source including disabled ones
 * @param comparePairs allowed compare pairs (A = older, B = newer)
 */
public record InternalSources(List<Source> sources, List<ComparePair> comparePairs) {

  public InternalSources {
    sources = sources == null ? List.of() : List.copyOf(sources);
    comparePairs = comparePairs == null ? List.of() : List.copyOf(comparePairs);
  }

  /** Run fields are null when the source has no ACTIVE run. */
  public record Source(
      String sourceKey,
      String framework,
      String versionLabel,
      String displayName,
      boolean enabled,
      Long activeRunId,
      String commitSha,
      String ingestedAt,
      Integer chunkCount) {

    /** Activity condition of policy §3.2: enabled AND an ACTIVE run exists. */
    public boolean active() {
      return enabled && activeRunId != null;
    }
  }

  public record ComparePair(String sourceKeyA, String sourceKeyB) {}
}
