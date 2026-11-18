package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.AiServerStub.StubResponse.frame;
import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.SHA;
import static com.r1nn.contextq.support.ChatStreamTestSupport.events;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static com.r1nn.contextq.support.ChatStreamTestSupport.singleBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamRequest;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.RewriteStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;

/** Relay + persistence against a stub ai-server (api-spec §3.1, policy §6.3·§10.2). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class ChatStreamControllerTest {

  static final AiServerStub STUB = new AiServerStub();
  static final String STREAM = "/internal/v1/chat/stream";
  static final Duration GAP = Duration.ofMillis(20);

  static final String META =
      "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKey\":\"langchain_v03\",\"ingestRunId\":7,"
          + "\"commitSha\":\""
          + SHA
          + "\",\"ingestedAt\":\"2026-10-05\",\"rewrittenQuery\":null,\"noContext\":false,"
          + "\"sources\":[{\"rank\":1,\"headingPath\":\"Agents > Basic\",\"permalink\":"
          + "\"https://github.com/langchain-ai/langchain/blob/"
          + SHA
          + "/docs/agents.md?plain=1#L1-L9\",\"siteUrl\":\"https://python.langchain.com/v0.3/\","
          + "\"similarity\":0.87321}]}";
  static final String TOKEN_A = "{\"event\":\"token\",\"t\":\"LangChain v0.3 기준 \"}";
  static final String TOKEN_B = "{\"event\":\"token\",\"t\":\"Agent는 [1]\"}";
  static final String DONE =
      "{\"event\":\"done\",\"status\":\"COMPLETED\",\"statusReason\":null,\"finishReason\":\"stop\","
          + "\"usage\":{\"prompt\":1240,\"completion\":312},\"latency\":{\"rewriteMs\":null,"
          + "\"embedMs\":80,\"retrieveMs\":120,\"ttftMs\":1850,\"totalMs\":5300},"
          + "\"invalidCitations\":[3],\"model\":\"gpt-4o-mini-2024-07-18\","
          + "\"promptVersion\":\"single_v2\"}";

  @DynamicPropertySource
  static void aiServer(DynamicPropertyRegistry registry) {
    registry.add("ai-server.base-url", STUB::baseUrl);
    registry.add("ai-server.first-event-timeout", () -> "1s");
    registry.add("ai-server.idle-timeout", () -> "1s");
  }

  @AfterAll
  static void stop() {
    STUB.close();
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private SourceCatalog sourceCatalog;
  @Autowired private MessageRepository messages;
  @Autowired private MessageSourceRepository sources;
  @Autowired private ConversationRepository conversations;
  @Autowired private JdbcTemplate jdbc;

  private long userId;

  @BeforeEach
  void setUp() {
    STUB.reset();
    sourceCatalog.invalidate();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, CATALOG));
    userId = newUser(jdbc);
  }

  @Test
  void completedStreamIsRelayedAndStored() throws Exception {
    upstream(
        StubResponse.sse(
            GAP, frame(META), frame(TOKEN_A), ": ping\n\n", frame(TOKEN_B), frame(DONE)));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, " 질문 ", "langchain_v03")));

    List<JsonNode> events = events(body);
    assertThat(events)
        .extracting(e -> e.get("event").asString())
        .containsExactly("meta", "token", "token", "done");
    assertThat(body).contains(":ping");
    JsonNode meta = events.getFirst();
    Message answer = messages.findById(meta.get("messageId").asLong()).orElseThrow();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.COMPLETED);
    assertThat(answer.getContent()).isEqualTo("LangChain v0.3 기준 Agent는 [1]");
    assertThat(answer.getModel()).isEqualTo("gpt-4o-mini-2024-07-18");
    assertThat(answer.getPromptVersion()).isEqualTo("single_v2");
    assertThat(answer.getPromptTokens()).isEqualTo(1240);
    assertThat(answer.getTtftMs()).isEqualTo(1850);
    assertThat(answer.getInvalidCitations()).isEqualTo("[3]");
    assertThat(answer.getTop1Similarity()).isEqualByComparingTo("0.8732");
    assertThat(answer.getCommitSha()).isEqualTo(SHA);
    assertThat(sources.findByMessage_IdOrderByIdAsc(answer.getId()))
        .singleElement()
        .satisfies(s -> assertThat(s.getRankLabel()).isEqualTo("1"));
    Conversation conversation =
        conversations.findById(meta.get("conversationId").asLong()).orElseThrow();
    assertThat(conversation.getLastMessageStatus()).isEqualTo(MessageStatus.COMPLETED);
    assertThat(conversation.getMessageCount()).isEqualTo(2);
    JsonNode sent =
        jsonOf(
            STUB.requests().stream()
                .filter(r -> r.path().endsWith("chat/stream"))
                .findFirst()
                .orElseThrow()
                .body());
    assertThat(sent.get("question").asString()).isEqualTo("질문");
    assertThat(sent.get("requestId").asString()).isEqualTo(answer.getRequestId());
  }

  @Test
  void noContextEndsPendingAsNoContext() throws Exception {
    String meta =
        "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKey\":\"langchain_v03\",\"ingestRunId\":7,"
            + "\"noContext\":true,\"sources\":[]}";
    String done =
        "{\"event\":\"done\",\"status\":\"NO_CONTEXT\",\"statusReason\":\"LOW_SIMILARITY\"}";
    upstream(StubResponse.sse(GAP, frame(meta), frame(done)));

    Message answer =
        lastAnswer(
            streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03"))));

    assertThat(answer.getStatus()).isEqualTo(MessageStatus.NO_CONTEXT);
    assertThat(answer.getStatusReason()).isEqualTo("LOW_SIMILARITY");
  }

  @Test
  void midstreamErrorIsPartial() throws Exception {
    String error =
        "{\"event\":\"error\",\"code\":\"LLM_ERROR\",\"message\":\"LLM 오류\",\"requestId\":\"r\","
            + "\"partial\":true}";
    upstream(StubResponse.sse(GAP, frame(META), frame(TOKEN_A), frame(error)));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    JsonNode last = events(body).getLast();
    assertThat(last.get("code").asString()).isEqualTo("LLM_ERROR");
    assertThat(last.get("partial").booleanValue()).isTrue();
    Message answer = lastAnswer(body);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.PARTIAL);
    assertThat(answer.getStatusReason()).isEqualTo("LLM_ERROR");
    assertThat(answer.getContent()).isEqualTo("LangChain v0.3 기준 ");
  }

  @Test
  void internalErrorBeforeMetaBecomesAiUnavailable() throws Exception {
    String error =
        "{\"event\":\"error\",\"code\":\"INTERNAL_ERROR\",\"message\":\"x\",\"requestId\":\"r\","
            + "\"partial\":false}";
    upstream(StubResponse.sse(GAP, frame(error)));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    JsonNode only = events(body).getFirst();
    assertThat(events(body)).hasSize(1);
    assertThat(only.get("code").asString()).isEqualTo("AI_UNAVAILABLE");
    assertThat(only.get("partial").booleanValue()).isFalse();
    Message answer = answerOfLatestConversation();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo("INTERNAL_ERROR");
  }

  @Test
  void firstEventTimeoutFailsWithUpstreamTimeout() throws Exception {
    upstream(StubResponse.sseThenHang(": ping\n\n"));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    JsonNode only = events(body).getFirst();
    assertThat(only.get("code").asString()).isEqualTo("UPSTREAM_TIMEOUT");
    assertThat(only.get("partial").booleanValue()).isFalse();
    Message answer = answerOfLatestConversation();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo("UPSTREAM_TIMEOUT");
  }

  @Test
  void idleTimeoutAfterTokensIsPartial() throws Exception {
    upstream(StubResponse.sseThenHang(frame(META), frame(TOKEN_A)));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    JsonNode last = events(body).getLast();
    assertThat(last.get("code").asString()).isEqualTo("UPSTREAM_TIMEOUT");
    assertThat(last.get("partial").booleanValue()).isTrue();
    Message answer = lastAnswer(body);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.PARTIAL);
    assertThat(answer.getStatusReason()).isEqualTo("UPSTREAM_IDLE_TIMEOUT");
  }

  @Test
  void upstreamCloseWithoutTerminalIsAiUnavailable() throws Exception {
    upstream(StubResponse.sse(GAP, frame(META), frame(TOKEN_A)));

    String body =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q", "langchain_v03")));

    assertThat(events(body).getLast().get("code").asString()).isEqualTo("AI_UNAVAILABLE");
    Message answer = lastAnswer(body);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.PARTIAL);
    assertThat(answer.getStatusReason()).isEqualTo("AI_UNAVAILABLE");
  }

  @Test
  void preStreamRejectionIsJsonAndStoredAsFailed() throws Exception {
    upstream(
        StubResponse.json(
            503,
            "{\"code\":\"AI_BUSY\",\"message\":\"혼잡\",\"request_id\":\"r\",\"timestamp\":\"t\"}"));

    mockMvc
        .perform(streamRequest(userId, singleBody(null, "q", "langchain_v03")))
        .andExpect(status().isServiceUnavailable())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.error.code").value("AI_BUSY"));

    Message answer = answerOfLatestConversation();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo("AI_BUSY");
  }

  @Test
  void unknownAndDisabledSourcesAreRejectedBeforeStoring() throws Exception {
    long before = messages.count();

    mockMvc
        .perform(streamRequest(userId, singleBody(null, "q", "langchain_v99")))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.error.code").value("SOURCE_NOT_FOUND"));
    mockMvc
        .perform(streamRequest(userId, singleBody(null, "q", "langchain_v1x")))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.error.code").value("SOURCE_UNAVAILABLE"));

    assertThat(messages.count()).isEqualTo(before);
  }

  @Test
  void followUpUsesConversationSource() throws Exception {
    upstream(StubResponse.sse(GAP, frame(META), frame(TOKEN_A), frame(DONE)));
    String first =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q1", "langchain_v03")));
    long conversationId = events(first).getFirst().get("conversationId").asLong();

    String body =
        """
        {"conversationId":%d,"question":"q2","mode":"SINGLE"}
        """
            .formatted(conversationId);
    String second = streamBody(mockMvc, streamRequest(userId, body));

    assertThat(events(second).getFirst().get("conversationId").asLong()).isEqualTo(conversationId);
    assertThat(conversations.findById(conversationId).orElseThrow().getMessageCount()).isEqualTo(4);
  }

  @Test
  void followUpSendsDbHistoryAndStoresTheRewrite() throws Exception {
    upstream(StubResponse.sse(GAP, frame(META), frame(TOKEN_A), frame(DONE)));
    String first =
        streamBody(mockMvc, streamRequest(userId, singleBody(null, "q1", "langchain_v03")));
    long conversationId = events(first).getFirst().get("conversationId").asLong();
    assertThat(lastAnswer(first).getRewriteStatus()).isEqualTo(RewriteStatus.SKIPPED);
    STUB.reset();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, CATALOG));
    String rewrittenMeta =
        META.replace("\"rewrittenQuery\":null", "\"rewrittenQuery\":\"q1 대상의 반환값\"");
    upstream(StubResponse.sse(GAP, frame(rewrittenMeta), frame(TOKEN_A), frame(DONE)));

    String body =
        """
        {"conversationId":%d,"question":"그 반환값은?","mode":"SINGLE",
         "history":[{"role":"user","content":"조작된 맥락"}]}
        """
            .formatted(conversationId);
    Message answer = lastAnswer(streamBody(mockMvc, streamRequest(userId, body)));

    JsonNode sent =
        jsonOf(
            STUB.requests().stream()
                .filter(r -> r.path().endsWith("chat/stream"))
                .findFirst()
                .orElseThrow()
                .body());
    assertThat(sent.get("history"))
        .extracting(m -> m.get("role").asString() + ":" + m.get("content").asString())
        .containsExactly("user:q1", "assistant:LangChain v0.3 기준 ");
    assertThat(answer.getRewriteStatus()).isEqualTo(RewriteStatus.OK);
    assertThat(answer.getRewrittenQuery()).isEqualTo("q1 대상의 반환값");
  }

  @Test
  void invalidRequestsAreRejected() throws Exception {
    mockMvc
        .perform(streamRequest(userId, singleBody(null, "   ", "langchain_v03")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("question"));
    mockMvc
        .perform(
            streamRequest(
                userId,
                "{\"question\":\"q\",\"mode\":\"COMPARE\",\"sourceKeyA\":\"langchain_v03\","
                    + "\"sourceKeyB\":\"langchain_v03\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("sourceKeyB"));
  }

  @Test
  void anonymousRequestIsAGuestAndCannotCompare() throws Exception {
    mockMvc
        .perform(
            post("/api/v1/chat/stream")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"question\":\"q\",\"mode\":\"COMPARE\",\"sourceKeyA\":\"langchain_v03\","
                        + "\"sourceKeyB\":\"langchain_v1x\"}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.error.code").value("GUEST_MODE_NOT_ALLOWED"));
  }

  private void upstream(StubResponse response) {
    STUB.on("POST", STREAM, r -> response);
  }

  private Message lastAnswer(String body) {
    long messageId = events(body).getFirst().get("messageId").asLong();
    return messages.findById(messageId).orElseThrow();
  }

  /** Answer of the newest conversation of the current user (streams that never sent meta). */
  private Message answerOfLatestConversation() {
    Long answerId =
        jdbc.queryForObject(
            "SELECT max(id) FROM messages WHERE user_id = ? AND role = 'ASSISTANT'",
            Long.class,
            userId);
    return messages.findById(answerId).orElseThrow();
  }

  private static JsonNode jsonOf(String json) {
    return com.r1nn.contextq.support.ChatStreamTestSupport.JSON.readTree(json);
  }
}
