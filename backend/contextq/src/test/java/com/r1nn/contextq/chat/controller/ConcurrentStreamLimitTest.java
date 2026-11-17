package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.AiServerStub.StubResponse.frame;
import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static com.r1nn.contextq.support.ChatStreamTestSupport.singleBody;
import static com.r1nn.contextq.support.ChatStreamTestSupport.streamRequest;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.chat.service.StreamSlots;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import jakarta.servlet.http.Cookie;
import java.security.MessageDigest;
import java.util.HexFormat;
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

/** policy §8.1: 2 open streams per user, 1 per guest session; slots come back when streams end. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class ConcurrentStreamLimitTest {

  static final AiServerStub STUB = new AiServerStub();
  static final String META =
      "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKey\":\"langchain_v03\",\"ingestRunId\":7,"
          + "\"noContext\":false,\"sources\":[]}";

  @DynamicPropertySource
  static void aiServer(DynamicPropertyRegistry registry) {
    registry.add("ai-server.base-url", STUB::baseUrl);
    registry.add("ai-server.first-event-timeout", () -> "2s");
    registry.add("ai-server.idle-timeout", () -> "2s");
  }

  @AfterAll
  static void stop() {
    STUB.close();
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private SourceCatalog sourceCatalog;
  @Autowired private StreamSlots slots;
  @Autowired private GuestSessionRepository sessions;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    STUB.reset();
    sourceCatalog.invalidate();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(200, CATALOG));
    // streams stay open after meta until the 2 s idle timeout ends them
    STUB.on("POST", "/internal/v1/chat/stream", r -> StubResponse.sseThenHang(frame(META)));
  }

  @Test
  void thirdOpenStreamOfAUserIsLimitedUntilOneEnds() throws Exception {
    long userId = newUser(jdbc);
    MvcResult first =
        mockMvc.perform(streamRequest(userId, singleBody(null, "a", "langchain_v03"))).andReturn();
    mockMvc.perform(streamRequest(userId, singleBody(null, "b", "langchain_v03"))).andReturn();

    mockMvc
        .perform(streamRequest(userId, singleBody(null, "c", "langchain_v03")))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.error.code").value("CONCURRENT_STREAM_LIMIT"));

    first.getAsyncResult(10_000); // idle timeout ends the stream and returns the slot
    awaitOpenCount("u:" + userId, 1);
    assertThat(
            mockMvc
                .perform(streamRequest(userId, singleBody(null, "d", "langchain_v03")))
                .andReturn()
                .getResponse()
                .getStatus())
        .isEqualTo(200);
  }

  @Test
  void secondOpenStreamOfAGuestIsLimitedAndRefunded() throws Exception {
    MvcResult first = mockMvc.perform(guest(null)).andReturn();
    String sid = sid(first);

    mockMvc
        .perform(guest(sid))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.error.code").value("CONCURRENT_STREAM_LIMIT"));

    assertThat(sessions.findBySidHash(hash(sid)).orElseThrow().getUsedCount()).isEqualTo((short) 1);
    first.getAsyncResult(10_000);
  }

  private void awaitOpenCount(String key, int expected) throws InterruptedException {
    for (int i = 0; i < 50 && slots.openCount(key) != expected; i++) {
      Thread.sleep(100);
    }
    assertThat(slots.openCount(key)).isEqualTo(expected);
  }

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder guest(
      String sid) {
    var request =
        post("/api/v1/chat/stream")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.TEXT_EVENT_STREAM)
            .with(
                r -> {
                  r.setRemoteAddr("192.0.2.77");
                  return r;
                })
            .content(singleBody(null, "q", "langchain_v03"));
    return sid == null ? request : request.cookie(new Cookie("devdocs_sid", sid));
  }

  private static String sid(MvcResult result) {
    Matcher m =
        Pattern.compile("devdocs_sid=([^;]+)")
            .matcher(result.getResponse().getHeader(HttpHeaders.SET_COOKIE));
    assertThat(m.find()).isTrue();
    return m.group(1);
  }

  private static String hash(String raw) throws Exception {
    return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw.getBytes()));
  }
}
