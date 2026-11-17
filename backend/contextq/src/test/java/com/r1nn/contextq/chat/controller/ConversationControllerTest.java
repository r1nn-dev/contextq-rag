package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.time.Instant;
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
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.support.TransactionTemplate;

/** Conversation history API (api-spec §4, INV-14). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class ConversationControllerTest {

  static final AiServerStub STUB = new AiServerStub();
  static final Instant T0 = Instant.parse("2026-10-01T09:00:00.123456Z");

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
  @Autowired private ConversationRepository conversations;
  @Autowired private MessageRepository messages;
  @Autowired private TransactionTemplate tx;
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
  void listsOwnConversationsNewestFirstAcrossPages() throws Exception {
    Long oldest = conversation(userId, "첫 번째", "langchain_v03", T0, 2);
    Long middle = conversation(userId, "두 번째", "langchain_v03", T0.plusSeconds(60), 2);
    Long newest = conversation(userId, "세 번째", "langchain_v03", T0.plusSeconds(120), 2);
    conversation(newUser(jdbc), "다른 사람", "langchain_v03", T0.plusSeconds(180), 2);

    mockMvc
        .perform(list(userId).param("size", "2"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.success").value(true))
        .andExpect(jsonPath("$.data.items.length()").value(2))
        .andExpect(jsonPath("$.data.items[0].conversationId").value(newest))
        .andExpect(jsonPath("$.data.items[1].conversationId").value(middle))
        .andExpect(jsonPath("$.data.hasNext").value(true))
        .andExpect(jsonPath("$.data.cursor").value("2026-10-01T09:01:00.123456Z"));

    mockMvc
        .perform(list(userId).param("size", "2").param("before", "2026-10-01T09:01:00.123456Z"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items.length()").value(1))
        .andExpect(jsonPath("$.data.items[0].conversationId").value(oldest))
        .andExpect(jsonPath("$.data.hasNext").value(false))
        .andExpect(jsonPath("$.data.cursor").doesNotExist());
  }

  @Test
  void rowFieldsFollowTheContract() throws Exception {
    Long id = conversation(userId, "LangChain v0.3에서\nAgent를 어떻게 생성하나요?", "langchain_v03", T0, 2);

    mockMvc
        .perform(list(userId))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items[0].conversationId").value(id))
        .andExpect(jsonPath("$.data.items[0].title").value("LangChain v0.3에서 Agent를 어떻게 생성하나요?"))
        .andExpect(jsonPath("$.data.items[0].mode").value("SINGLE"))
        .andExpect(jsonPath("$.data.items[0].sourceKey").value("langchain_v03"))
        .andExpect(jsonPath("$.data.items[0].sourceKeyA").isEmpty())
        .andExpect(jsonPath("$.data.items[0].versionLabel").value("v0.3"))
        .andExpect(jsonPath("$.data.items[0].messageCount").value(2))
        .andExpect(jsonPath("$.data.items[0].lastMessageStatus").value("COMPLETED"))
        .andExpect(jsonPath("$.data.items[0].status").value("OPEN"))
        .andExpect(jsonPath("$.data.items[0].updatedAt").value("2026-10-01T09:00:00.123456Z"));
  }

  @Test
  void fullOrInactiveConversationsAreReadOnly() throws Exception {
    Long disabled = conversation(userId, "비활성 버전", "langchain_v1x", T0, 2);
    Long removed = conversation(userId, "사라진 버전", "langchain_v02", T0.plusSeconds(1), 2);
    Long full = conversation(userId, "가득 찬 대화", "langchain_v03", T0.plusSeconds(2), 100);

    mockMvc
        .perform(list(userId))
        .andExpect(jsonPath("$.data.items[0].conversationId").value(full))
        .andExpect(jsonPath("$.data.items[0].status").value("READ_ONLY"))
        .andExpect(jsonPath("$.data.items[1].conversationId").value(removed))
        .andExpect(jsonPath("$.data.items[1].status").value("READ_ONLY"))
        .andExpect(jsonPath("$.data.items[1].versionLabel").value("langchain_v02"))
        .andExpect(jsonPath("$.data.items[2].conversationId").value(disabled))
        .andExpect(jsonPath("$.data.items[2].status").value("READ_ONLY"))
        .andExpect(jsonPath("$.data.items[2].versionLabel").value("v1.x"));
  }

  @Test
  void catalogOutageFallsBackToMessageCount() throws Exception {
    STUB.reset();
    STUB.on("GET", "/internal/v1/sources", r -> StubResponse.json(500, "{}"));
    conversation(userId, "비활성 버전", "langchain_v1x", T0, 2);
    conversation(userId, "가득 찬 대화", "langchain_v03", T0.plusSeconds(1), 100);

    mockMvc
        .perform(list(userId))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items[0].status").value("READ_ONLY"))
        .andExpect(jsonPath("$.data.items[0].versionLabel").value("langchain_v03"))
        .andExpect(jsonPath("$.data.items[1].status").value("OPEN"));
  }

  @Test
  void rejectsInvalidParameters() throws Exception {
    mockMvc
        .perform(list(userId).param("size", "21"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
    mockMvc
        .perform(list(userId).param("size", "0"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
    mockMvc
        .perform(list(userId).param("before", "yesterday"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
        .andExpect(jsonPath("$.error.details[0].field").value("before"));
  }

  @Test
  void guestsGet401() throws Exception {
    mockMvc
        .perform(get("/api/v1/conversations"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_MISSING"));
  }

  private MockHttpServletRequestBuilder list(long userId) {
    return get("/api/v1/conversations").with(user(String.valueOf(userId)));
  }

  /**
   * Conversation with {@code count} messages whose last answer ended at {@code updatedAt}. Messages
   * beyond the first pair only move the counter (list rows do not read messages).
   */
  private Long conversation(
      long owner, String question, String sourceKey, Instant updatedAt, int count) {
    return tx.execute(
        s -> {
          Conversation c =
              conversations.save(Conversation.single(owner, question, sourceKey, updatedAt));
          c.appendMessages(count);
          messages.save(Message.question(c, owner, question, 1));
          messages.save(Message.pendingAnswer(c, owner, "req-" + System.nanoTime()));
          c.recordAnswerEnded(MessageStatus.COMPLETED, updatedAt);
          return c.getId();
        });
  }
}
