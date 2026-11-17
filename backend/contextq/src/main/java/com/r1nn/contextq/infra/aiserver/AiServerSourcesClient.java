package com.r1nn.contextq.infra.aiserver;

import com.r1nn.contextq.common.web.RequestIdFilter;
import com.r1nn.contextq.global.config.AiServerProperties;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

/** Calls ai-server {@code GET /internal/v1/sources} (api-spec §6.3). Blocking; no transaction. */
@Component
public class AiServerSourcesClient {

  private final WebClient webClient;
  private final AiServerProperties properties;

  public AiServerSourcesClient(WebClient aiServerWebClient, AiServerProperties properties) {
    this.webClient = aiServerWebClient;
    this.properties = properties;
  }

  /**
   * Fetches the whole catalog.
   *
   * @throws AiServerUnavailableException on connect failure, timeout, non-2xx or empty body
   */
  public InternalSources fetch() {
    InternalSources body;
    try {
      body =
          webClient
              .get()
              .uri("/internal/v1/sources")
              .accept(MediaType.APPLICATION_JSON)
              .header(RequestIdFilter.HEADER, RequestIdFilter.currentOrNew())
              .retrieve()
              .bodyToMono(InternalSources.class)
              .block(properties.requestTimeout());
    } catch (RuntimeException e) {
      throw new AiServerUnavailableException("ai-server source list call failed", e);
    }
    if (body == null) {
      throw new AiServerUnavailableException("ai-server source list was empty", null);
    }
    return body;
  }
}
