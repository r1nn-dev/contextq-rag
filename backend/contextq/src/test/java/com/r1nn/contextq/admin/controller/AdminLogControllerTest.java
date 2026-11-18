package com.r1nn.contextq.admin.controller;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.support.ChatStreamTestSupport;
import java.sql.Timestamp;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/**
 * Admin request log (api-spec §5.5). Rows are dated 2031 and read with {@code before=2032}, so the
 * first page holds only this test's rows (other tests write "now").
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class AdminLogControllerTest {

  static final String LOGS = "/api/v1/admin/logs";
  static final String BEFORE = "2032-01-01T00:00:00Z";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private long userId;

  @BeforeEach
  void setUp() {
    jdbc.update("DELETE FROM messages WHERE updated_at >= '2031-01-01'");
    jdbc.update("DELETE FROM guest_usage_logs WHERE created_at >= '2031-01-01'");
    userId = ChatStreamTestSupport.newUser(jdbc);
    long single = conversation("SINGLE");
    long compare = conversation("COMPARE");
    answer(single, "COMPLETED", null, "2031-06-01T10:00:00Z");
    answer(single, "FAILED", "LLM_ERROR", "2031-06-01T10:03:00Z");
    answer(compare, "NO_CONTEXT", "LOW_SIMILARITY", "2031-06-01T10:02:00Z");
    answer(single, "STREAMING", null, "2031-06-01T10:04:00Z"); // still running: not a log entry
    guest("PARTIAL", "2031-06-01T10:01:00Z");
  }

  @Test
  void mergesMemberAnswersAndGuestLogsNewestFirst() throws Exception {
    mockMvc
        .perform(asAdmin(get(LOGS).param("before", BEFORE).param("size", "3")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items.length()").value(3))
        .andExpect(jsonPath("$.data.items[0].at").value("2031-06-01T10:03:00Z"))
        .andExpect(jsonPath("$.data.items[0].level").value("ERROR"))
        .andExpect(jsonPath("$.data.items[0].actor").value("USER"))
        .andExpect(jsonPath("$.data.items[0].userId").value(userId))
        .andExpect(jsonPath("$.data.items[0].requestId").value("req-FAILED"))
        .andExpect(jsonPath("$.data.items[0].statusReason").value("LLM_ERROR"))
        .andExpect(jsonPath("$.data.items[0].totalMs").value(4120))
        .andExpect(jsonPath("$.data.items[0].content").doesNotExist())
        .andExpect(jsonPath("$.data.items[1].mode").value("COMPARE"))
        .andExpect(jsonPath("$.data.items[1].level").value("WARN"))
        .andExpect(jsonPath("$.data.items[2].actor").value("GUEST"))
        .andExpect(jsonPath("$.data.items[2].userId").isEmpty())
        .andExpect(jsonPath("$.data.items[2].requestId").isEmpty())
        .andExpect(jsonPath("$.data.items[2].mode").value("SINGLE"))
        .andExpect(jsonPath("$.data.items[2].level").value("WARN"))
        .andExpect(jsonPath("$.data.items[2].promptTokens").value(10))
        .andExpect(jsonPath("$.data.hasNext").value(true))
        .andExpect(jsonPath("$.data.cursor").value("2031-06-01T10:01:00Z"));

    mockMvc
        .perform(asAdmin(get(LOGS).param("before", "2031-06-01T10:01:00Z").param("size", "3")))
        .andExpect(jsonPath("$.data.items[0].at").value("2031-06-01T10:00:00Z"))
        .andExpect(jsonPath("$.data.items[0].level").value("INFO"));
  }

  @Test
  void levelFilterAndCursor() throws Exception {
    mockMvc
        .perform(asAdmin(get(LOGS).param("before", BEFORE).param("level", "WARN")))
        .andExpect(jsonPath("$.data.items[0].status").value("NO_CONTEXT"))
        .andExpect(jsonPath("$.data.items[1].status").value("PARTIAL"));
    mockMvc
        .perform(asAdmin(get(LOGS).param("before", "2031-06-01T10:02:00Z").param("level", "WARN")))
        .andExpect(jsonPath("$.data.items[0].status").value("PARTIAL"));
  }

  @Test
  void invalidParametersAndNonAdmins() throws Exception {
    mockMvc
        .perform(asAdmin(get(LOGS).param("level", "DEBUG")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
    mockMvc
        .perform(asAdmin(get(LOGS).param("before", "yesterday")))
        .andExpect(status().isBadRequest());
    mockMvc.perform(get(LOGS).with(user("2"))).andExpect(status().isForbidden());
  }

  private MockHttpServletRequestBuilder asAdmin(MockHttpServletRequestBuilder request) {
    return request.with(user("1").roles("ADMIN"));
  }

  private long conversation(String mode) {
    boolean compare = mode.equals("COMPARE");
    Long id =
        jdbc.queryForObject(
            "INSERT INTO conversations (user_id, title, mode, source_key, source_key_a,"
                + " source_key_b, message_count, created_at, updated_at)"
                + " VALUES (?, 't', ?, ?, ?, ?, 0, now(), now()) RETURNING id",
            Long.class,
            userId,
            mode,
            compare ? null : "langchain_v03",
            compare ? "langchain_v03" : null,
            compare ? "langchain_v1x" : null);
    return id;
  }

  private void answer(long conversationId, String status, String reason, String at) {
    jdbc.update(
        "INSERT INTO messages (conversation_id, user_id, role, content, request_id, status,"
            + " status_reason, total_ms, created_at, updated_at)"
            + " VALUES (?, ?, 'ASSISTANT', 'secret answer text', ?, ?, ?, 4120, ?, ?)",
        conversationId,
        userId,
        "req-" + status,
        status,
        reason,
        Timestamp.from(Instant.parse(at).minusSeconds(5)),
        Timestamp.from(Instant.parse(at)));
  }

  private void guest(String status, String at) {
    jdbc.update(
        "INSERT INTO guest_usage_logs (sid_hash, status, prompt_tokens, completion_tokens,"
            + " created_at) VALUES (?, ?, 10, 2, ?)",
        "c".repeat(64),
        status,
        Timestamp.from(Instant.parse(at)));
  }
}
