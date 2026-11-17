package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.JSON;
import static com.r1nn.contextq.support.ChatStreamTestSupport.events;
import static com.r1nn.contextq.support.ChatStreamTestSupport.upstreamFrames;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.GuestUsageLog;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import com.r1nn.contextq.chat.repository.GuestUsageLogRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import com.r1nn.contextq.support.ChatStreamTestSupport;
import jakarta.servlet.http.Cookie;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.JsonNode;

/** Guest flow end to end against a stub ai-server (policy §1.3, api-spec §2.1·§3.1). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class GuestChatStreamTest {

  static final AiServerStub STUB = new AiServerStub();
  static final Pattern SID = Pattern.compile("devdocs_sid=([^;]+)");
  static final String STREAM = "/internal/v1/chat/stream";

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
  @Autowired private GuestSessionRepository sessions;
  @Autowired private GuestUsageLogRepository usageLogs;
  @Autowired private MessageRepository messages;
  @Autowired private JdbcTemplate jdbc;

  private String ip;

  @BeforeEach
  void setUp() {
    STUB.reset();
    sourceCatalog.invalidate();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, CATALOG));
    ip = "192.0.2." + (System.nanoTime() % 200);
  }

  @Test
  void guestStreamIsRelayedWithoutStoringMessages() throws Exception {
    upstream(StubResponse.sse(Duration.ofMillis(5), upstreamFrames("single-completed.json")));
    long messagesBefore = messages.count();

    MvcResult result = perform(guest(null, body("[]")));
    String body = streamBodyOf(result);

    JsonNode meta = events(body).getFirst();
    assertThat(meta.get("conversationId").isNull()).isTrue();
    assertThat(meta.get("messageId").isNull()).isTrue();
    assertThat(events(body).getLast().get("event").asString()).isEqualTo("done");
    String sid = sid(result);
    assertThat(sessions.findBySidHash(hash(sid)).orElseThrow().getUsedCount()).isEqualTo((short) 1);
    assertThat(messages.count()).isEqualTo(messagesBefore);
    List<GuestUsageLog> logs = usageLogs.findBySidHash(hash(sid));
    assertThat(logs)
        .singleElement()
        .satisfies(
            l -> {
              assertThat(l.getStatus()).isEqualTo(MessageStatus.COMPLETED);
              assertThat(l.getPromptTokens()).isEqualTo(1240);
            });
  }

  @Test
  void aiServerRejectionRefundsAndStillSetsTheCookie() throws Exception {
    upstream(StubResponse.json(503, "{\"code\":\"AI_BUSY\",\"message\":\"m\"}"));

    MvcResult result =
        mockMvc
            .perform(guest(null, body("[]")))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error.code").value("AI_BUSY"))
            .andExpect(header().exists(HttpHeaders.SET_COOKIE))
            .andReturn();

    String hash = hash(sid(result));
    assertThat(sessions.findBySidHash(hash).orElseThrow().getUsedCount()).isZero();
    assertThat(usageLogs.findBySidHash(hash))
        .singleElement()
        .satisfies(l -> assertThat(l.getStatus()).isEqualTo(MessageStatus.FAILED));
  }

  @Test
  void errorBeforeMetaIsRefundedButNoContextIsNot() throws Exception {
    upstream(StubResponse.sse(Duration.ofMillis(5), upstreamFrames("error-before-meta.json")));
    MvcResult failed = perform(guest(null, body("[]")));
    streamBodyOf(failed); // the refund happens when the stream ends
    String sid = sid(failed);
    assertThat(used(sid)).isZero();

    upstream(StubResponse.sse(Duration.ofMillis(5), upstreamFrames("single-no-context.json")));
    streamBodyOf(perform(guest(sid, body("[]"))));
    assertThat(used(sid)).isEqualTo((short) 1);
  }

  @Test
  void sixthQuestionIsRejected() throws Exception {
    upstream(StubResponse.sse(Duration.ofMillis(1), upstreamFrames("single-no-context.json")));
    MvcResult first = perform(guest(null, body("[]")));
    streamBodyOf(first);
    String sid = sid(first);
    for (int i = 0; i < 4; i++) {
      streamBodyOf(perform(guest(sid, body("[]"))));
    }

    mockMvc
        .perform(guest(sid, body("[]")))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.error.code").value("GUEST_QUOTA_EXCEEDED"));
  }

  @Test
  void historyIsTruncatedBeforeForwarding() throws Exception {
    upstream(StubResponse.sse(Duration.ofMillis(1), upstreamFrames("single-no-context.json")));
    StringBuilder history = new StringBuilder("[");
    for (int i = 0; i < 8; i++) {
      String role = i % 2 == 0 ? "user" : "assistant";
      String content = i == 7 ? "x".repeat(2500) : "m" + i;
      history
          .append(i == 0 ? "" : ",")
          .append("{\"role\":\"")
          .append(role)
          .append("\",\"content\":\"")
          .append(content)
          .append("\"}");
    }
    history.append("]");

    streamBodyOf(perform(guest(null, body(history.toString()))));

    JsonNode sent = JSON.readTree(lastStreamBody());
    assertThat(sent.get("history")).hasSize(6);
    assertThat(sent.at("/history/0/content").asString()).isEqualTo("m2");
    assertThat(sent.at("/history/5/content").asString()).hasSize(2000);
  }

  @Test
  void malformedHistoryAndConversationIdAreInvalid() throws Exception {
    mockMvc
        .perform(guest(null, body("[{\"role\":\"system\",\"content\":\"x\"}]")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("history"));
    mockMvc
        .perform(
            guestRaw(
                null,
                "{\"conversationId\":3,\"question\":\"q\",\"mode\":\"SINGLE\","
                    + "\"sourceKey\":\"langchain_v03\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("conversationId"));
  }

  @Test
  void memberHistoryIsIgnored() throws Exception {
    upstream(StubResponse.sse(Duration.ofMillis(1), upstreamFrames("single-no-context.json")));
    long userId = ChatStreamTestSupport.newUser(jdbc);

    streamBodyOf(
        perform(
            post("/api/v1/chat/stream")
                .with(user(String.valueOf(userId)))
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .content(body("[{\"role\":\"user\",\"content\":\"injected\"}]"))));

    assertThat(JSON.readTree(lastStreamBody()).get("history")).isEmpty();
  }

  @Test
  void sourcesReportGuestUsageWithoutIssuingACookie() throws Exception {
    mockMvc
        .perform(get("/api/v1/sources"))
        .andExpect(status().isOk())
        .andExpect(header().doesNotExist(HttpHeaders.SET_COOKIE))
        .andExpect(jsonPath("$.data.guest.limit").value(5))
        .andExpect(jsonPath("$.data.guest.used").value(0))
        .andExpect(jsonPath("$.data.guest.remaining").value(5))
        .andExpect(jsonPath("$.data.guest.expiresAt").isEmpty());

    upstream(StubResponse.sse(Duration.ofMillis(1), upstreamFrames("single-no-context.json")));
    MvcResult first = perform(guest(null, body("[]")));
    streamBodyOf(first);
    String sid = sid(first);
    mockMvc
        .perform(get("/api/v1/sources").cookie(new Cookie("devdocs_sid", sid)))
        .andExpect(jsonPath("$.data.guest.used").value(1))
        .andExpect(jsonPath("$.data.guest.remaining").value(4))
        .andExpect(jsonPath("$.data.guest.expiresAt").isString());
    mockMvc
        .perform(get("/api/v1/sources").with(user("1")))
        .andExpect(jsonPath("$.data.guest").isEmpty());
  }

  private void upstream(StubResponse response) {
    STUB.on("POST", STREAM, r -> response);
  }

  private String lastStreamBody() {
    return STUB.requests().stream()
        .filter(r -> ("/" + r.path()).equals(STREAM))
        .reduce((a, b) -> b)
        .orElseThrow()
        .body();
  }

  private MvcResult perform(MockHttpServletRequestBuilder request) throws Exception {
    return mockMvc.perform(request).andReturn();
  }

  private static String streamBodyOf(MvcResult result) throws Exception {
    if (result.getRequest().isAsyncStarted()) {
      result.getAsyncResult(20_000);
    }
    return result.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
  }

  private short used(String sid) {
    return sessions.findBySidHash(hash(sid)).orElseThrow().getUsedCount();
  }

  private MockHttpServletRequestBuilder guest(String sid, String body) {
    return guestRaw(sid, body);
  }

  private MockHttpServletRequestBuilder guestRaw(String sid, String body) {
    MockHttpServletRequestBuilder request =
        post("/api/v1/chat/stream")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.TEXT_EVENT_STREAM)
            .with(
                r -> {
                  r.setRemoteAddr(ip);
                  return r;
                })
            .content(body);
    return sid == null ? request : request.cookie(new Cookie("devdocs_sid", sid));
  }

  private static String body(String historyJson) {
    return "{\"question\":\"q\",\"mode\":\"SINGLE\",\"sourceKey\":\"langchain_v03\",\"history\":"
        + historyJson
        + "}";
  }

  private static String sid(MvcResult result) {
    String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
    assertThat(setCookie).isNotNull();
    Matcher m = SID.matcher(setCookie);
    assertThat(m.find()).isTrue();
    return m.group(1);
  }

  private static String hash(String raw) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw.getBytes()));
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }
}
