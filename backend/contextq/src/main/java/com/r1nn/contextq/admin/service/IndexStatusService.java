package com.r1nn.contextq.admin.service;

import com.r1nn.contextq.admin.dto.IndexStatusResponse;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.infra.aiserver.AiServerIndexClient;
import com.r1nn.contextq.infra.aiserver.AiServerUnavailableException;
import com.r1nn.contextq.infra.aiserver.InternalIndexStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Admin index dashboard (api-spec §5.1, ADM-01): index state from ai-server plus app usage.
 *
 * <p>Not transactional: the ai-server call runs outside any transaction; the usage summary opens
 * its own read-only one.
 */
@Service
public class IndexStatusService {

  private static final Logger log = LoggerFactory.getLogger(IndexStatusService.class);

  private final AiServerIndexClient indexClient;
  private final UsageSummaryService usage;

  public IndexStatusService(AiServerIndexClient indexClient, UsageSummaryService usage) {
    this.indexClient = indexClient;
    this.usage = usage;
  }

  /**
   * @throws BusinessException {@code AI_UNAVAILABLE} when ai-server cannot be read
   */
  public IndexStatusResponse status() {
    InternalIndexStatus index;
    try {
      index = indexClient.fetchStatus();
    } catch (AiServerUnavailableException e) {
      log.warn("admin_index_status_unavailable", e);
      throw new BusinessException(ErrorCode.AI_UNAVAILABLE);
    }
    return IndexStatusResponse.of(index, usage.summary());
  }
}
