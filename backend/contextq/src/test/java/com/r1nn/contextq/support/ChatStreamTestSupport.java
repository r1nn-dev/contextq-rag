package com.r1nn.contextq.support;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** Helpers for chat stream tests: users, catalog JSON, request and SSE output parsing. */
public final class ChatStreamTestSupport {

  public static final String SHA = "0123456789abcdef0123456789abcdef01234567";
  public static final ObjectMapper JSON = JsonMapper.builder().build();

  /** Catalog with both sources active and one compare pair. */
  public static final String CATALOG =
      """
      {"sources":[
        {"sourceKey":"langchain_v03","framework":"langchain","versionLabel":"v0.3",
         "displayName":"LangChain v0.3","enabled":true,"activeRunId":7,
         "commitSha":"0123456789abcdef0123456789abcdef01234567","ingestedAt":"2026-10-05",
         "chunkCount":3842},
        {"sourceKey":"langchain_v1x","framework":"langchain","versionLabel":"v1.x",
         "displayName":"LangChain v1.x","enabled":false,"activeRunId":8,
         "commitSha":"89abcdef0123456789abcdef0123456789abcdef","ingestedAt":"2026-10-05",
         "chunkCount":5120}],
       "comparePairs":[{"sourceKeyA":"langchain_v03","sourceKeyB":"langchain_v1x"}]}
      """;

  private ChatStreamTestSupport() {}

  public static long newUser(JdbcTemplate jdbc) {
    return jdbc.queryForObject(
        "INSERT INTO users (email, password_hash, role, status, login_failed_count, created_at,"
            + " updated_at) VALUES (?, 'hash', 'ROLE_USER', 'ACTIVE', 0, now(), now())"
            + " RETURNING id",
        Long.class,
        "chat-" + System.nanoTime() + "@example.com");
  }

  public static MockHttpServletRequestBuilder streamRequest(long userId, String body) {
    return post("/api/v1/chat/stream")
        .with(user(String.valueOf(userId)))
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .content(body);
  }

  public static String singleBody(Long conversationId, String question, String sourceKey) {
    return JSON.writeValueAsString(
            java.util.Map.of(
                "conversationId",
                conversationId == null ? "" : conversationId,
                "question",
                question,
                "mode",
                "SINGLE",
                "sourceKey",
                sourceKey))
        .replace("\"conversationId\":\"\"", "\"conversationId\":null");
  }

  /** Runs an async SSE request to completion and returns its raw body. */
  public static String streamBody(MockMvc mockMvc, MockHttpServletRequestBuilder request)
      throws Exception {
    MvcResult result = mockMvc.perform(request).andReturn();
    if (result.getRequest().isAsyncStarted()) {
      result.getAsyncResult(20_000);
    }
    return result.getResponse().getContentAsString(StandardCharsets.UTF_8);
  }

  /** {@code data:} payloads of an SSE body, in order (comments are skipped). */
  public static List<JsonNode> events(String body) {
    List<JsonNode> events = new ArrayList<>();
    for (String line : body.split("\n")) {
      if (line.startsWith("data:")) {
        events.add(JSON.readTree(line.substring("data:".length()).strip()));
      }
    }
    return events;
  }

  /** Upstream example stream from {@code contracts/examples/upstream/} as SSE frames. */
  public static String[] upstreamFrames(String exampleName) throws Exception {
    JsonNode array =
        JSON.readTree(
            java.nio.file.Files.readString(
                java.nio.file.Path.of(
                    "..", "..", "contracts", "examples", "upstream", exampleName)));
    List<String> frames = new ArrayList<>();
    for (JsonNode event : array) {
      frames.add(AiServerStub.StubResponse.frame(JSON.writeValueAsString(event)));
    }
    return frames.toArray(String[]::new);
  }
}
