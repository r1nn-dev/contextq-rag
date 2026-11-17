package com.r1nn.contextq.chat.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SourceControllerTest {

  static final AiServerStub STUB = new AiServerStub();

  static final String SHA_A = "0123456789abcdef0123456789abcdef01234567";
  static final String SHA_B = "89abcdef0123456789abcdef0123456789abcdef";

  @DynamicPropertySource
  static void aiServer(DynamicPropertyRegistry registry) {
    registry.add("ai-server.base-url", STUB::baseUrl);
    registry.add("ai-server.internal-token", () -> "test-internal-token");
  }

  @AfterAll
  static void stop() {
    STUB.close();
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private SourceCatalog sourceCatalog;

  @BeforeEach
  void setUp() {
    STUB.reset();
    sourceCatalog.invalidate();
  }

  @Test
  void listsActiveSourcesWithCompareEnabledWithoutLogin() throws Exception {
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, catalog(true, 8L)));

    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.success").value(true))
        .andExpect(jsonPath("$.message").isEmpty())
        .andExpect(jsonPath("$.data.sources.length()").value(2))
        .andExpect(jsonPath("$.data.sources[0].sourceKey").value("langchain_v03"))
        .andExpect(jsonPath("$.data.sources[0].framework").value("langchain"))
        .andExpect(jsonPath("$.data.sources[0].activeRun.commitSha").value(SHA_A))
        .andExpect(jsonPath("$.data.sources[0].activeRun.ingestedAt").value("2026-10-05"))
        .andExpect(jsonPath("$.data.sources[0].activeRun.chunkCount").value(3842))
        .andExpect(jsonPath("$.data.comparePairs[0].compareEnabled").value(true))
        .andExpect(jsonPath("$.data.comparePairs[0].sourceKeyA").value("langchain_v03"));
  }

  @Test
  void sourceWithoutActiveRunIsHiddenAndDisablesCompare() throws Exception {
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, catalog(true, null)));

    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.sources.length()").value(1))
        .andExpect(jsonPath("$.data.comparePairs[0].compareEnabled").value(false));
  }

  @Test
  void disabledSourceIsHidden() throws Exception {
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, catalog(false, 8L)));

    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.sources.length()").value(1))
        .andExpect(jsonPath("$.data.sources[0].sourceKey").value("langchain_v1x"));
  }

  @Test
  void noActiveSourceIsIndexNotActive() throws Exception {
    STUB.on(
        "GET",
        "/internal/v1/sources",
        r ->
            StubResponse.json(
                200,
                """
                {"sources":[{"sourceKey":"langchain_v03","framework":"langchain",
                  "versionLabel":"v0.3","displayName":"LangChain v0.3","enabled":true,
                  "activeRunId":null,"commitSha":null,"ingestedAt":null,"chunkCount":null}],
                 "comparePairs":[]}
                """));

    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.error.code").value("INDEX_NOT_ACTIVE"));
  }

  @Test
  void aiServerDownWithoutCacheIsAiUnavailable() throws Exception {
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(500, "{}"));

    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.error.code").value("AI_UNAVAILABLE"));
  }

  @Test
  void repeatedCallsHitAiServerOnce() throws Exception {
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, catalog(true, 8L)));

    mockMvc.perform(get("/api/v1/sources")).andExpect(status().isOk());
    mockMvc.perform(get("/api/v1/sources")).andExpect(status().isOk());

    assertThat(STUB.count("/internal/v1/sources")).isEqualTo(1);
    assertThat(STUB.requests().getFirst().header("X-Internal-Token"))
        .isEqualTo("test-internal-token");
  }

  /** v0.3 enabled flag is configurable; v1.x ACTIVE run id may be null. */
  static String catalog(boolean v03Enabled, Long v1xRunId) {
    String v1xRun =
        v1xRunId == null
            ? "\"activeRunId\":null,\"commitSha\":null,\"ingestedAt\":null,\"chunkCount\":null"
            : "\"activeRunId\":"
                + v1xRunId
                + ",\"commitSha\":\""
                + SHA_B
                + "\",\"ingestedAt\":\"2026-10-05\",\"chunkCount\":5120";
    return """
        {"sources":[
          {"sourceKey":"langchain_v03","framework":"langchain","versionLabel":"v0.3",
           "displayName":"LangChain v0.3","enabled":%s,"activeRunId":7,"commitSha":"%s",
           "ingestedAt":"2026-10-05","chunkCount":3842},
          {"sourceKey":"langchain_v1x","framework":"langchain","versionLabel":"v1.x",
           "displayName":"LangChain v1.x","enabled":true,%s}],
         "comparePairs":[{"sourceKeyA":"langchain_v03","sourceKeyB":"langchain_v1x"}]}
        """
        .formatted(v03Enabled, SHA_A, v1xRun);
  }
}
