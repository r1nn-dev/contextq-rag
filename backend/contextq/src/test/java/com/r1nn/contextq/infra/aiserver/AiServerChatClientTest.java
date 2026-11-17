package com.r1nn.contextq.infra.aiserver;

import static com.r1nn.contextq.support.AiServerStub.StubResponse.frame;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient.ChatCall;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class AiServerChatClientTest {

  static final String REQUEST_ID = "a1b2c3d4-0000-4000-8000-000000000001";

  private final AiServerStub stub = new AiServerStub();

  @AfterEach
  void tearDown() {
    stub.close();
  }

  @Test
  void streamsFramesAndHeartbeatsWithInternalHeaders() {
    stub.on(
        "POST",
        "/internal/v1/chat/stream",
        r ->
            StubResponse.sse(
                Duration.ofMillis(10),
                frame("{\"event\":\"token\",\"t\":\"a\"}"),
                ": ping\n\n",
                frame("{\"event\":\"done\",\"status\":\"COMPLETED\"}")));

    List<ServerSentEvent<String>> events =
        client(stub.baseUrl()).open(call()).collectList().block();

    assertThat(events).hasSize(3);
    assertThat(events.get(0).data()).isEqualTo("{\"event\":\"token\",\"t\":\"a\"}");
    assertThat(events.get(1).data()).isNull();
    assertThat(events.get(1).comment()).isEqualTo("ping");
    AiServerStub.Recorded request = stub.requests().getFirst();
    assertThat(request.header("X-Internal-Token")).isEqualTo("test-internal-token");
    assertThat(request.header("X-Request-Id")).isEqualTo(REQUEST_ID);
    JsonNode body = JsonMapper.builder().build().readTree(request.body());
    assertThat(body.get("mode").asString()).isEqualTo("SINGLE");
    assertThat(body.get("sourceKey").asString()).isEqualTo("langchain_v03");
    assertThat(body.get("history").isArray()).isTrue();
  }

  @Test
  void preStreamErrorKeepsAiServerCode() {
    stub.on(
        "POST",
        "/internal/v1/chat/stream",
        r ->
            StubResponse.json(
                503,
                "{\"code\":\"AI_BUSY\",\"message\":\"시스템이 혼잡합니다.\",\"request_id\":\"x\","
                    + "\"timestamp\":\"2026-11-18T00:00:00Z\"}"));

    assertThatThrownBy(() -> client(stub.baseUrl()).open(call()))
        .isInstanceOfSatisfying(
            UpstreamRejectedException.class,
            e -> {
              assertThat(e.getStatus()).isEqualTo(503);
              assertThat(e.getCode()).isEqualTo("AI_BUSY");
            });
  }

  @Test
  void nonJsonErrorHasNoCode() {
    stub.on("POST", "/internal/v1/chat/stream", r -> StubResponse.json(502, "<html>bad</html>"));

    assertThatThrownBy(() -> client(stub.baseUrl()).open(call()))
        .isInstanceOfSatisfying(
            UpstreamRejectedException.class, e -> assertThat(e.getCode()).isNull());
  }

  @Test
  void slowHeadersTimeOut() {
    stub.on(
        "POST",
        "/internal/v1/chat/stream",
        r -> StubResponse.json(200, "{}").afterHeaderDelay(Duration.ofSeconds(3)));

    assertThatThrownBy(() -> client(stub.baseUrl(), Duration.ofMillis(300)).open(call()))
        .isInstanceOf(UpstreamTimeoutException.class);
  }

  @Test
  void refusedConnectionIsUnavailable() {
    String deadUrl = stub.baseUrl();
    stub.close();

    assertThatThrownBy(() -> client(deadUrl).open(call()))
        .isInstanceOf(AiServerUnavailableException.class);
  }

  static ChatCall call() {
    return new ChatCall(REQUEST_ID, "langchain_v03", "Agent 생성 방법", List.of());
  }

  static AiServerChatClient client(String baseUrl) {
    return client(baseUrl, Duration.ofSeconds(15));
  }

  static AiServerChatClient client(String baseUrl, Duration firstEventTimeout) {
    AiServerProperties properties =
        new AiServerProperties(
            baseUrl,
            "test-internal-token",
            Duration.ofSeconds(3),
            Duration.ofSeconds(5),
            firstEventTimeout,
            Duration.ofSeconds(30),
            Duration.ofSeconds(60));
    return new AiServerChatClient(
        new AiServerWebClientConfig().aiServerWebClient(properties), properties);
  }
}
