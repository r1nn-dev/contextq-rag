package com.r1nn.contextq.contract;

import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.events;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static com.r1nn.contextq.support.ChatStreamTestSupport.singleBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamRequest;
import static com.r1nn.contextq.support.ChatStreamTestSupport.upstreamFrames;
import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.contract.SseContract.Leg;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;

/**
 * Every single-mode upstream example, relayed by backend, must satisfy the client-leg contract
 * (contracts/sse-events.schema.json, INV-06).
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class ChatRelayContractTest {

  static final AiServerStub STUB = new AiServerStub();

  @DynamicPropertySource
  static void aiServer(DynamicPropertyRegistry registry) {
    registry.add("ai-server.base-url", STUB::baseUrl);
  }

  @AfterAll
  static void stop() {
    STUB.close();
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private SourceCatalog sourceCatalog;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    STUB.reset();
    sourceCatalog.invalidate();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, CATALOG));
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "single-completed.json",
        "single-no-context.json",
        "error-midstream.json",
        "error-before-meta.json"
      })
  void relayedStreamSatisfiesClientContract(String example) throws Exception {
    String[] frames = upstreamFrames(example);
    STUB.on(
        "POST", "/internal/v1/chat/stream", r -> StubResponse.sse(Duration.ofMillis(5), frames));
    long userId = newUser(jdbc);

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    List<JsonNode> events = events(body);
    SseContract.validateStream(events, Leg.CLIENT);
    if (events.getFirst().get("event").asString().equals("meta")) {
      assertThat(events.getFirst().get("conversationId").isIntegralNumber()).isTrue();
      assertThat(events.getFirst().get("messageId").isIntegralNumber()).isTrue();
    }
  }
}
