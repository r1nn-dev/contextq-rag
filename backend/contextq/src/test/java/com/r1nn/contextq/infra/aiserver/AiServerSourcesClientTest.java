package com.r1nn.contextq.infra.aiserver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

class AiServerSourcesClientTest {

  static final String BODY =
      """
      {"sources":[{"sourceKey":"langchain_v03","framework":"langchain","versionLabel":"v0.3",
        "displayName":"LangChain v0.3","enabled":true,"activeRunId":7,
        "commitSha":"0123456789abcdef0123456789abcdef01234567","ingestedAt":"2026-10-05",
        "chunkCount":3842}],
       "comparePairs":[{"sourceKeyA":"langchain_v03","sourceKeyB":"langchain_v1x"}]}
      """;

  private final AiServerStub stub = new AiServerStub();

  @AfterEach
  void tearDown() {
    stub.close();
  }

  @Test
  void parsesCatalogAndSendsInternalHeaders() {
    stub.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, BODY));

    InternalSources catalog = client(stub.baseUrl()).fetch();

    assertThat(catalog.sources())
        .singleElement()
        .satisfies(
            s -> {
              assertThat(s.framework()).isEqualTo("langchain");
              assertThat(s.activeRunId()).isEqualTo(7L);
              assertThat(s.ingestedAt()).isEqualTo("2026-10-05");
              assertThat(s.active()).isTrue();
            });
    assertThat(catalog.comparePairs()).hasSize(1);
    AiServerStub.Recorded request = stub.requests().getFirst();
    assertThat(request.header("X-Internal-Token")).isEqualTo("test-internal-token");
    assertThat(request.header("X-Request-Id")).hasSize(36);
  }

  @Test
  void serverErrorIsUnavailable() {
    stub.on("GET", "/internal/v1/sources", r -> StubResponse.json(500, "{\"code\":\"X\"}"));

    assertThatThrownBy(() -> client(stub.baseUrl()).fetch())
        .isInstanceOf(AiServerUnavailableException.class);
  }

  @Test
  void connectionRefusedIsUnavailable() {
    String deadUrl = stub.baseUrl();
    stub.close();

    assertThatThrownBy(() -> client(deadUrl).fetch())
        .isInstanceOf(AiServerUnavailableException.class);
  }

  static AiServerSourcesClient client(String baseUrl) {
    AiServerProperties properties = properties(baseUrl);
    WebClient webClient = new AiServerWebClientConfig().aiServerWebClient(properties);
    return new AiServerSourcesClient(webClient, properties);
  }

  static AiServerProperties properties(String baseUrl) {
    return new AiServerProperties(
        baseUrl,
        "test-internal-token",
        Duration.ofSeconds(3),
        Duration.ofSeconds(5),
        Duration.ofSeconds(15),
        Duration.ofSeconds(30),
        Duration.ofSeconds(60));
  }
}
