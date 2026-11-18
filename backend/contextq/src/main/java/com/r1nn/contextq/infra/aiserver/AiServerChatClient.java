package com.r1nn.contextq.infra.aiserver;

import com.r1nn.contextq.common.web.RequestIdFilter;
import com.r1nn.contextq.global.config.AiServerProperties;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * Opens ai-server {@code POST /internal/v1/chat/stream} (api-spec §6.1, ADR-003·012).
 *
 * <p>{@link #open} blocks only until the response headers arrive, so a pre-stream rejection (AI
 * busy, unknown source, …) can still become a plain JSON error to the browser. The returned body
 * {@link Flux} streams the SSE frames; heartbeats arrive as comment-only events. Must be called
 * outside any DB transaction.
 */
@Component
public class AiServerChatClient {

  private static final ParameterizedTypeReference<ServerSentEvent<String>> SSE_TYPE =
      new ParameterizedTypeReference<>() {};
  private static final ObjectMapper JSON = JsonMapper.builder().build();

  private final WebClient webClient;
  private final AiServerProperties properties;

  public AiServerChatClient(WebClient aiServerWebClient, AiServerProperties properties) {
    this.webClient = aiServerWebClient;
    this.properties = properties;
  }

  /**
   * One question (api-spec §6.1).
   *
   * @param mode {@code SINGLE} or {@code COMPARE}
   * @param sourceKey SINGLE source, null for COMPARE
   * @param sourceKeyA COMPARE older source (A), null for SINGLE
   * @param sourceKeyB COMPARE newer source (B), null for SINGLE
   * @param history recent turns ({@code role}, {@code content}); empty for the first question
   */
  public record ChatCall(
      String requestId,
      String mode,
      String sourceKey,
      String sourceKeyA,
      String sourceKeyB,
      String question,
      List<Map<String, String>> history) {

    /** Single-mode question. */
    public ChatCall(
        String requestId, String sourceKey, String question, List<Map<String, String>> history) {
      this(requestId, "SINGLE", sourceKey, null, null, question, history);
    }

    /** Compare-mode question (A = older, B = newer). */
    public static ChatCall compare(
        String requestId,
        String sourceKeyA,
        String sourceKeyB,
        String question,
        List<Map<String, String>> history) {
      return new ChatCall(requestId, "COMPARE", null, sourceKeyA, sourceKeyB, question, history);
    }
  }

  /**
   * Sends the request and waits for the response headers.
   *
   * @return SSE body stream (cold until subscribed)
   * @throws UpstreamRejectedException non-2xx answer before the stream
   * @throws UpstreamTimeoutException headers did not arrive within the first-event timeout
   * @throws AiServerUnavailableException connection failure (3 s connect timeout)
   */
  public Flux<ServerSentEvent<String>> open(ChatCall call) {
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("requestId", call.requestId());
    body.put("mode", call.mode());
    if ("COMPARE".equals(call.mode())) {
      body.put("sourceKeyA", call.sourceKeyA());
      body.put("sourceKeyB", call.sourceKeyB());
    } else {
      body.put("sourceKey", call.sourceKey());
    }
    body.put("question", call.question());
    body.put("history", call.history());

    ResponseEntity<Flux<ServerSentEvent<String>>> entity;
    try {
      entity =
          webClient
              .post()
              .uri("/internal/v1/chat/stream")
              .contentType(MediaType.APPLICATION_JSON)
              .accept(MediaType.TEXT_EVENT_STREAM)
              .header(RequestIdFilter.HEADER, call.requestId())
              .bodyValue(body)
              .retrieve()
              .toEntityFlux(SSE_TYPE)
              .timeout(properties.firstEventTimeout())
              .block();
    } catch (WebClientResponseException e) {
      throw rejected(e);
    } catch (WebClientRequestException e) {
      throw new AiServerUnavailableException("ai-server connection failed", e);
    } catch (RuntimeException e) {
      if (Exceptions.unwrap(e) instanceof TimeoutException) {
        throw new UpstreamTimeoutException("ai-server response headers timed out");
      }
      throw new AiServerUnavailableException("ai-server stream call failed", e);
    }
    if (entity == null || entity.getBody() == null) {
      throw new AiServerUnavailableException("ai-server stream had no body", null);
    }
    return entity.getBody();
  }

  private static UpstreamRejectedException rejected(WebClientResponseException e) {
    String code = null;
    String message = e.getStatusText();
    try {
      JsonNode node = JSON.readTree(e.getResponseBodyAsString());
      if (node.hasNonNull("code")) {
        code = node.get("code").asString();
      }
      if (node.hasNonNull("message")) {
        message = node.get("message").asString();
      }
    } catch (RuntimeException ignored) {
      // non-JSON body: keep code null so the caller maps it to AI_UNAVAILABLE
    }
    return new UpstreamRejectedException(e.getStatusCode().value(), code, message);
  }
}
