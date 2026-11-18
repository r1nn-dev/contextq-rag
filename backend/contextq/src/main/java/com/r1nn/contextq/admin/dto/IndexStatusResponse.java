package com.r1nn.contextq.admin.dto;

import com.r1nn.contextq.infra.aiserver.InternalIndexStatus;
import java.util.List;

/**
 * {@code GET /api/v1/admin/index/status} body (api-spec §5.1).
 *
 * @param sources ai-server §6.6 sources as they are
 */
public record IndexStatusResponse(
    List<InternalIndexStatus.SourceStatus> sources, UsageSummary usageSummary) {

  public static IndexStatusResponse of(InternalIndexStatus index, UsageSummary usage) {
    return new IndexStatusResponse(index.sources(), usage);
  }
}
