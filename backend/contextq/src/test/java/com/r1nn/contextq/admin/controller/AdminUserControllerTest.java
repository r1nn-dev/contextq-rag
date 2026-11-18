package com.r1nn.contextq.admin.controller;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.r1nn.contextq.TestcontainersConfiguration;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import org.hamcrest.Matchers;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/** Admin user list and unlock (api-spec §5.3·§5.4). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class AdminUserControllerTest {

  static final String USERS = "/api/v1/admin/users";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private String tag;
  private long locked;
  private long expired;
  private long member;

  @BeforeEach
  void setUp() {
    tag = "adm" + System.nanoTime();
    Instant now = Instant.now();
    member = insertUser("member", "ACTIVE", null, now.minusSeconds(30));
    expired =
        insertUser("expired", "LOCKED", now.minus(Duration.ofMinutes(20)), now.minusSeconds(20));
    locked = insertUser("locked", "LOCKED", now.minus(Duration.ofMinutes(5)), now.minusSeconds(10));
    Long conversation =
        jdbc.queryForObject(
            "INSERT INTO conversations (user_id, title, mode, source_key, message_count,"
                + " created_at, updated_at) VALUES (?, 't', 'SINGLE', 'langchain_v03', 0, now(),"
                + " now()) RETURNING id",
            Long.class,
            member);
    for (int cost : new int[] {1, 2}) {
      jdbc.update(
          "INSERT INTO messages (conversation_id, user_id, role, content, quota_cost, created_at,"
              + " updated_at) VALUES (?, ?, 'USER', 'q', ?, now(), now())",
          conversation,
          member,
          cost);
    }
  }

  @Test
  void listsMatchingUsersNewestFirstWithLockAndUsage() throws Exception {
    mockMvc
        .perform(asAdmin(get(USERS).param("query", "  " + tag.toUpperCase())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items.length()").value(3))
        .andExpect(jsonPath("$.data.items[0].userId").value(locked))
        .andExpect(jsonPath("$.data.items[0].status").value("LOCKED"))
        .andExpect(jsonPath("$.data.items[0].lockedUntil").isString())
        .andExpect(jsonPath("$.data.items[1].userId").value(expired))
        .andExpect(jsonPath("$.data.items[1].status").value("ACTIVE")) // 15 minutes passed
        .andExpect(jsonPath("$.data.items[1].lockedUntil").isEmpty())
        .andExpect(jsonPath("$.data.items[2].userId").value(member))
        .andExpect(jsonPath("$.data.items[2].role").value("ROLE_USER"))
        .andExpect(jsonPath("$.data.items[2].totalQuestions").value(2))
        .andExpect(jsonPath("$.data.items[2].todayQuotaUsed").value(3))
        .andExpect(jsonPath("$.data.items[2].dailyQuota").value(100))
        .andExpect(jsonPath("$.data.items[2].passwordHash").doesNotExist())
        .andExpect(jsonPath("$.data.hasNext").value(false))
        .andExpect(jsonPath("$.data.cursor").isEmpty())
        .andExpect(jsonPath("$.data.summary.locked").value(Matchers.greaterThanOrEqualTo(1)))
        .andExpect(jsonPath("$.data.summary.totalUsers").value(Matchers.greaterThanOrEqualTo(3)));
  }

  @Test
  void cursorPagesThroughTheSearch() throws Exception {
    String first =
        mockMvc
            .perform(asAdmin(get(USERS).param("query", tag).param("size", "2")))
            .andExpect(jsonPath("$.data.items.length()").value(2))
            .andExpect(jsonPath("$.data.hasNext").value(true))
            .andReturn()
            .getResponse()
            .getContentAsString();
    String cursor = JsonPath.read(first, "$.data.cursor");

    mockMvc
        .perform(asAdmin(get(USERS).param("query", tag).param("size", "2").param("before", cursor)))
        .andExpect(jsonPath("$.data.items.length()").value(1))
        .andExpect(jsonPath("$.data.items[0].userId").value(member))
        .andExpect(jsonPath("$.data.hasNext").value(false));
  }

  @Test
  void likeWildcardsInTheSearchAreLiteral() throws Exception {
    mockMvc
        .perform(asAdmin(get(USERS).param("query", tag + "%")))
        .andExpect(jsonPath("$.data.items.length()").value(0));
  }

  @Test
  void unlockMakesTheAccountActive() throws Exception {
    mockMvc
        .perform(asAdmin(post(USERS + "/" + locked + "/unlock")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.userId").value(locked))
        .andExpect(jsonPath("$.data.status").value("ACTIVE"))
        .andExpect(jsonPath("$.data.lockedUntil").isEmpty());
    mockMvc
        .perform(asAdmin(post(USERS + "/" + member + "/unlock")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("ACTIVE"));
  }

  @Test
  void unlockAndListErrors() throws Exception {
    mockMvc
        .perform(asAdmin(post(USERS + "/" + Long.MAX_VALUE + "/unlock")))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.error.code").value("USER_NOT_FOUND"));
    mockMvc
        .perform(post(USERS + "/" + locked + "/unlock").with(user("2")))
        .andExpect(status().isForbidden());
    mockMvc
        .perform(asAdmin(get(USERS).param("size", "51")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
  }

  private MockHttpServletRequestBuilder asAdmin(MockHttpServletRequestBuilder request) {
    return request.with(user("1").roles("ADMIN"));
  }

  private long insertUser(String name, String status, Instant lockedAt, Instant createdAt) {
    Long id =
        jdbc.queryForObject(
            "INSERT INTO users (email, password_hash, role, status, login_failed_count, locked_at,"
                + " created_at, updated_at) VALUES (?, 'hash', 'ROLE_USER', ?, ?, ?, ?, ?)"
                + " RETURNING id",
            Long.class,
            name + "." + tag + "@example.com",
            status,
            lockedAt == null ? 0 : 5,
            lockedAt == null ? null : Timestamp.from(lockedAt),
            Timestamp.from(createdAt),
            Timestamp.from(createdAt));
    return id;
  }
}
