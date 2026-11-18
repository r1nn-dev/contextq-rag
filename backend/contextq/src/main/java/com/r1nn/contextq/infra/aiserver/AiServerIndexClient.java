package com.r1nn.contextq.infra.aiserver;

import com.r1nn.contextq.common.web.RequestIdFilter;
import com.r1nn.contextq.global.config.AiServerProperties;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Calls ai-server {@code GET /internal/v1/index/status} (api-spec §6.6) for the admin dashboard.
 * Blocking, not cached; must be called outside any DB transaction.
 */
@Component
public class AiServerIndexClient {

  private final WebClient webClient;
  private final AiServerProperties properties;

  public AiServerIndexClient(WebClient aiServerWebClient, AiServerProperties properties) {
    this.webClient = aiServerWebClient;
    this.properties = properties;
  }

  /**
   * @throws AiServerUnavailableException on connect failure, timeout, non-2xx or empty body
   */
  public InternalIndexStatus fetchStatus() {
    InternalIndexStatus body;
    try {
      body =
          webClient
              .get()
              .uri("/internal/v1/index/status")
              .accept(MediaType.APPLICATION_JSON)
              .header(RequestIdFilter.HEADER, RequestIdFilter.currentOrNew())
              .retrieve()
              .bodyToMono(InternalIndexStatus.class)
              .block(properties.requestTimeout());
    } catch (RuntimeException e) {
      throw new AiServerUnavailableException("ai-server index status call failed", e);
    }
    if (body == null) {
      throw new AiServerUnavailableException("ai-server index status was empty", null);
    }
    return body;
  }
}
