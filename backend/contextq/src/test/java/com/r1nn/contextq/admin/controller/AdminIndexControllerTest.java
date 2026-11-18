package com.r1nn.contextq.admin.controller;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
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

/** {@code GET /api/v1/admin/index/status} against a stub ai-server (api-spec §5.1·§6.6). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class AdminIndexControllerTest {

  static final AiServerStub STUB = new AiServerStub();
  static final String URL = "/api/v1/admin/index/status";

  static final String STATUS =
      """
      {"sources":[
        {"sourceKey":"langchain_v03","displayName":"LangChain v0.3","enabled":true,
         "activeRun":{"ingestRunId":6,"status":"ACTIVE",
           "commitSha":"0123456789abcdef0123456789abcdef01234567","chunkStrategy":"C",
           "chunkCount":3842,"prevChunkCount":3790,"embeddingModel":"text-embedding-3-small",
           "embeddingTokens":2150000,"embeddingCostUsd":0.043,"ingestDurationMs":48500,
           "startedAt":"2026-11-18T02:00:00Z","completedAt":"2026-11-18T02:00:48Z"},
         "recentRuns":[
           {"ingestRunId":6,"status":"ACTIVE","startedAt":"2026-11-18T02:00:00Z"},
           {"ingestRunId":3,"status":"FAILED","startedAt":"2026-11-17T02:00:00Z",
            "failureStage":"VALIDATING"}]},
        {"sourceKey":"langchain_v1x","displayName":"LangChain v1.x","enabled":false,
         "activeRun":null,"recentRuns":[]}]}
      """;

  @DynamicPropertySource
  static void aiServer(DynamicPropertyRegistry registry) {
    registry.add("ai-server.base-url", STUB::baseUrl);
  }

  @AfterAll
  static void stop() {
    STUB.close();
  }

  @Autowired private MockMvc mockMvc;

  @BeforeEach
  void setUp() {
    STUB.reset();
  }

  @Test
  void adminSeesIndexStateAndUsage() throws Exception {
    STUB.on("GET", "/internal/v1/index/status", r -> StubResponse.json(200, STATUS));

    mockMvc
        .perform(get(URL).with(user("1").roles("ADMIN")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.sources.length()").value(2))
        .andExpect(jsonPath("$.data.sources[0].activeRun.chunkStrategy").value("C"))
        .andExpect(jsonPath("$.data.sources[0].activeRun.embeddingCostUsd").value(0.043))
        .andExpect(jsonPath("$.data.sources[0].activeRun.startedAt").value("2026-11-18T02:00:00Z"))
        .andExpect(jsonPath("$.data.sources[0].recentRuns[1].failureStage").value("VALIDATING"))
        .andExpect(jsonPath("$.data.sources[0].recentRuns[0].failureStage").doesNotExist())
        .andExpect(jsonPath("$.data.sources[1].activeRun").isEmpty())
        .andExpect(jsonPath("$.data.usageSummary.today.date").isString())
        .andExpect(jsonPath("$.data.usageSummary.today.guestSessions").isNumber())
        .andExpect(jsonPath("$.data.usageSummary.last7Days.length()").value(7))
        .andExpect(jsonPath("$.data.usageSummary.last7Days[0].guestSessions").doesNotExist());
  }

  @Test
  void userIsForbiddenAndAnonymousIsUnauthorized() throws Exception {
    mockMvc
        .perform(get(URL).with(user("2")))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.error.code").value("FORBIDDEN"));
    mockMvc
        .perform(get(URL))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_MISSING"));
  }

  @Test
  void aiServerFailureIsServiceUnavailable() throws Exception {
    STUB.on("GET", "/internal/v1/index/status", r -> StubResponse.json(500, "{}"));

    mockMvc
        .perform(get(URL).with(user("1").roles("ADMIN")))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.error.code").value("AI_UNAVAILABLE"));
  }
}
