package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.AiServerStub.StubResponse.frame;
import static com.r1nn.contextq.support.ChatStreamTestSupport.COMPARE_CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.JSON;
import static com.r1nn.contextq.support.ChatStreamTestSupport.events;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamRequest;
import static com.r1nn.contextq.support.ChatStreamTestSupport.upstreamFrames;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;

/** Compare relay + persistence against a stub ai-server (api-spec §3.1 비교 모드, policy §10.2). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class CompareStreamControllerTest {

  static final AiServerStub STUB = new AiServerStub();
  static final String STREAM = "/internal/v1/chat/stream";
  static final Duration GAP = Duration.ofMillis(20);

  static final String NO_CONTEXT_META =
      "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKeyA\":\"langchain_v03\","
          + "\"sourceKeyB\":\"langchain_v1x\",\"ingestRunIdA\":7,\"ingestRunIdB\":8,"
          + "\"rewrittenQuery\":null,\"noContext\":true,\"sources\":[]}";

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
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, COMPARE_CATALOG));
    userId = newUser(jdbc);
  }

  @Test
  void completedCompareIsRelayedAndStored() throws Exception {
    upstream(StubResponse.sse(GAP, upstreamFrames("compare-completed.json")));

    String body = streamBody(mockMvc, streamRequest(userId, compareBody(null)));

    List<JsonNode> events = events(body);
    assertThat(events).extracting(e -> e.get("event").asString()).containsExactly("meta", "done");
    JsonNode meta = events.getFirst();
    assertThat(meta.get("conversationId").isNumber()).isTrue();
    assertThat(events.get(1).get("compareResult").get("changes")).hasSize(1);

    Message answer = messages.findById(meta.get("messageId").asLong()).orElseThrow();
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.COMPLETED);
    assertThat(answer.getContent()).isNull();
    assertThat(JSON.readTree(answer.getCompareResult()).get("version_b").get("citations"))
        .extracting(JsonNode::asString)
        .containsExactly("B1");
    assertThat(answer.getIngestRunIdA()).isEqualTo(7L);
    assertThat(answer.getIngestRunIdB()).isEqualTo(8L);
    assertThat(answer.getCommitShaB()).isEqualTo("89abcdef0123456789abcdef0123456789abcdef");
    assertThat(answer.getTop1SimilarityA()).isEqualByComparingTo("0.8732");
    assertThat(answer.getTop1SimilarityB()).isEqualByComparingTo("0.82");
    assertThat(answer.getPromptTokens()).isEqualTo(2100);
    assertThat(sources.findByMessage_IdOrderByIdAsc(answer.getId()))
        .extracting(MessageSource::getRankLabel, MessageSource::getSourceKey)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("A1", "langchain_v03"),
            org.assertj.core.groups.Tuple.tuple("B1", "langchain_v1x"));

    Conversation conversation =
        conversations.findById(meta.get("conversationId").asLong()).orElseThrow();
    assertThat(conversation.getMode()).isEqualTo(ConversationMode.COMPARE);
    assertThat(conversation.getSourceKeyA()).isEqualTo("langchain_v03");
    assertThat(question(conversation.getId()).getQuotaCost()).isEqualTo((short) 2);

    JsonNode sent = sentBody(0);
    assertThat(sent.get("mode").asString()).isEqualTo("COMPARE");
    assertThat(sent.get("sourceKeyA").asString()).isEqualTo("langchain_v03");
    assertThat(sent.get("sourceKeyB").asString()).isEqualTo("langchain_v1x");
    assertThat(sent.has("sourceKey")).isFalse();
  }

  @Test
  void bothSidesWithoutEvidenceAreStoredAsNoContext() throws Exception {
    upstream(
        StubResponse.sse(
            GAP,
            frame(NO_CONTEXT_META),
            frame(
                "{\"event\":\"done\",\"status\":\"NO_CONTEXT\",\"statusReason\":\"LOW_SIMILARITY\"}")));

    Message answer = lastAnswer(streamBody(mockMvc, streamRequest(userId, compareBody(null))));

    assertThat(answer.getStatus()).isEqualTo(MessageStatus.NO_CONTEXT);
    assertThat(answer.getStatusReason()).isEqualTo("LOW_SIMILARITY");
    assertThat(answer.getCompareResult()).isNull();
  }

  @Test
  void parseFailureAfterMetaIsStoredAsFailed() throws Exception {
    String[] completed = upstreamFrames("compare-completed.json");
    upstream(
        StubResponse.sse(
            GAP,
            completed[0],
            frame(
                "{\"event\":\"error\",\"code\":\"COMPARE_PARSE_ERROR\",\"message\":\"m\","
                    + "\"requestId\":\"r\",\"partial\":false}")));

    String body = streamBody(mockMvc, streamRequest(userId, compareBody(null)));

    JsonNode error = events(body).getLast();
    assertThat(error.get("code").asString()).isEqualTo("COMPARE_PARSE_ERROR");
    assertThat(error.get("partial").asBoolean()).isFalse();
    Message answer = lastAnswer(body);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo("COMPARE_PARSE_ERROR");
    assertThat(answer.getCommitShaA()).isNotNull(); // meta snapshot kept
  }

  @Test
  void silentUpstreamAfterMetaEndsAsUpstreamTimeout() throws Exception {
    upstream(StubResponse.sseThenHang(upstreamFrames("compare-completed.json")[0]));

    String body = streamBody(mockMvc, streamRequest(userId, compareBody(null)));

    assertThat(events(body).getLast().get("code").asString()).isEqualTo("UPSTREAM_TIMEOUT");
    Message answer = lastAnswer(body);
    assertThat(answer.getStatus()).isEqualTo(MessageStatus.FAILED);
    assertThat(answer.getStatusReason()).isEqualTo("UPSTREAM_TIMEOUT");
  }

  @Test
  void followUpSendsTheSummariesAsHistory() throws Exception {
    upstream(StubResponse.sse(GAP, upstreamFrames("compare-completed.json")));
    long conversationId =
        events(streamBody(mockMvc, streamRequest(userId, compareBody(null))))
            .getFirst()
            .get("conversationId")
            .asLong();

    streamBody(mockMvc, streamRequest(userId, compareBody(conversationId)));

    JsonNode history = sentBody(1).get("history");
    assertThat(history).hasSize(2);
    assertThat(history.get(1).get("role").asString()).isEqualTo("assistant");
    assertThat(history.get(1).get("content").asString())
        .isEqualTo("v0.3은 AgentExecutor로 에이전트를 실행한다.\nv1.x는 create_agent로 에이전트를 만든다.");
  }

  @Test
  void reversedPairIsRejectedBeforeAnythingIsStored() throws Exception {
    mockMvc
        .perform(
            streamRequest(
                userId,
                JSON.writeValueAsString(
                    Map.of(
                        "question", "q",
                        "mode", "COMPARE",
                        "sourceKeyA", "langchain_v1x",
                        "sourceKeyB", "langchain_v03"))))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("sourceKeyB"));
    assertThat(STUB.count(STREAM)).isZero();
  }

  @Test
  void singleQuestionInACompareConversationIsRejected() throws Exception {
    upstream(StubResponse.sse(GAP, upstreamFrames("compare-completed.json")));
    long conversationId =
        events(streamBody(mockMvc, streamRequest(userId, compareBody(null))))
            .getFirst()
            .get("conversationId")
            .asLong();

    mockMvc
        .perform(
            streamRequest(
                userId,
                JSON.writeValueAsString(
                    Map.of("conversationId", conversationId, "question", "q", "mode", "SINGLE"))))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("mode"));
  }

  private void upstream(StubResponse response) {
    STUB.on("POST", STREAM, r -> response);
  }

  private static String compareBody(Long conversationId) {
    Map<String, Object> body =
        conversationId == null
            ? Map.of(
                "question",
                "에이전트 생성 방식 차이는?",
                "mode",
                "COMPARE",
                "sourceKeyA",
                "langchain_v03",
                "sourceKeyB",
                "langchain_v1x")
            : Map.of("conversationId", conversationId, "question", "그럼 도구는?", "mode", "COMPARE");
    return JSON.writeValueAsString(body);
  }

  private JsonNode sentBody(int index) {
    return JSON.readTree(
        STUB.requests().stream()
            .filter(r -> r.path().endsWith("chat/stream"))
            .toList()
            .get(index)
            .body());
  }

  private Message lastAnswer(String body) {
    return messages.findById(events(body).getFirst().get("messageId").asLong()).orElseThrow();
  }

  private Message question(long conversationId) {
    return messages.findByConversation_IdOrderByCreatedAtAscIdAsc(conversationId).stream()
        .filter(m -> m.getRole() == MessageRole.USER)
        .findFirst()
        .orElseThrow();
  }
}
