package com.r1nn.contextq.chat.controller;

import static com.r1nn.contextq.support.ChatStreamTestSupport.CATALOG;
import static com.r1nn.contextq.support.ChatStreamTestSupport.SHA;
import static com.r1nn.contextq.support.ChatStreamTestSupport.newUser;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.CompareSnapshot;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.support.AiServerStub;
import com.r1nn.contextq.support.AiServerStub.StubResponse;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
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

  static final String SHA_B = "89abcdef0123456789abcdef0123456789abcdef";

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
  @Autowired private MessageSourceRepository sources;
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

  @Test
  void detailReturnsMessagesSourcesAndSnapshotsInOrder() throws Exception {
    long[] ids = answeredConversation(userId);
    long conversationId = ids[0];

    mockMvc
        .perform(detail(userId, conversationId))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.conversationId").value(conversationId))
        .andExpect(jsonPath("$.data.title").value("Agent 생성"))
        .andExpect(jsonPath("$.data.mode").value("SINGLE"))
        .andExpect(jsonPath("$.data.status").value("OPEN"))
        .andExpect(jsonPath("$.data.messageCount").value(4))
        .andExpect(jsonPath("$.data.messages.length()").value(4))
        .andExpect(jsonPath("$.data.messages[0].messageId").value(ids[1]))
        .andExpect(jsonPath("$.data.messages[0].role").value("USER"))
        .andExpect(jsonPath("$.data.messages[0].content").value("Agent 생성"))
        .andExpect(jsonPath("$.data.messages[0].status").doesNotExist())
        .andExpect(jsonPath("$.data.messages[1].messageId").value(ids[2]))
        .andExpect(jsonPath("$.data.messages[1].role").value("ASSISTANT"))
        .andExpect(jsonPath("$.data.messages[1].content").value("답변 [1] [2]"))
        .andExpect(jsonPath("$.data.messages[1].status").value("COMPLETED"))
        .andExpect(jsonPath("$.data.messages[1].requestId").value("req-detail"))
        .andExpect(jsonPath("$.data.messages[1].rewrittenQuery").value("LangChain Agent 생성"))
        .andExpect(jsonPath("$.data.messages[1].snapshot.versionLabel").value("v0.3"))
        .andExpect(jsonPath("$.data.messages[1].snapshot.commitSha").value(SHA))
        .andExpect(jsonPath("$.data.messages[1].snapshot.ingestedAt").value("2026-10-05"))
        .andExpect(jsonPath("$.data.messages[1].usage.prompt").value(1240))
        .andExpect(jsonPath("$.data.messages[1].latency.rewriteMs").isEmpty())
        .andExpect(jsonPath("$.data.messages[1].latency.totalMs").value(5300))
        .andExpect(jsonPath("$.data.messages[1].sources.length()").value(2))
        .andExpect(jsonPath("$.data.messages[1].sources[0].rank").value(1))
        .andExpect(jsonPath("$.data.messages[1].sources[0].rankLabel").value("1"))
        .andExpect(jsonPath("$.data.messages[1].sources[1].rank").value(2))
        .andExpect(jsonPath("$.data.messages[1].sources[1].similarity").value(0.7))
        .andExpect(jsonPath("$.data.messages[3].role").value("ASSISTANT"))
        .andExpect(jsonPath("$.data.messages[3].status").value("PENDING"))
        .andExpect(jsonPath("$.data.messages[3].content").value(""))
        .andExpect(jsonPath("$.data.messages[3].snapshot").isEmpty())
        .andExpect(jsonPath("$.data.messages[3].usage").isEmpty())
        .andExpect(jsonPath("$.data.messages[3].latency").isEmpty())
        .andExpect(jsonPath("$.data.messages[3].sources.length()").value(0));
  }

  @Test
  void foreignAndMissingConversationsLookTheSame() throws Exception {
    Long foreign = conversation(newUser(jdbc), "다른 사람", "langchain_v03", T0, 2);

    mockMvc
        .perform(detail(userId, foreign))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_FOUND"));
    mockMvc
        .perform(detail(userId, Long.MAX_VALUE))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_FOUND"));
    mockMvc
        .perform(get("/api/v1/conversations/abc").with(user(String.valueOf(userId))))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
  }

  @Test
  void compareDetailReturnsTheResultAndBothSnapshots() throws Exception {
    long conversationId =
        tx.execute(
            s -> {
              Conversation c =
                  conversations.save(
                      Conversation.compare(
                          userId, "생성 방식 차이", "langchain_v03", "langchain_v1x", T0));
              c.appendMessages(2);
              messages.save(Message.question(c, userId, "생성 방식 차이", 2));
              Message answer = messages.save(Message.pendingAnswer(c, userId, "req-compare"));
              answer.startProcessing();
              answer.applyCompareMeta(
                  new CompareSnapshot(
                      7L,
                      8L,
                      SHA,
                      SHA_B,
                      LocalDate.of(2026, 10, 5),
                      LocalDate.of(2026, 10, 6),
                      new BigDecimal("0.8700"),
                      new BigDecimal("0.8200"),
                      null));
              sources.save(source(answer, "A1", "0.8700"));
              sources.save(
                  MessageSource.of(
                      answer,
                      "langchain_v1x",
                      "B1",
                      "Agents > create_agent",
                      "https://github.com/langchain-ai/docs/blob/" + SHA_B + "/a.mdx?plain=1#L1-L2",
                      null,
                      new BigDecimal("0.8200")));
              answer.finish(
                  MessageStatus.COMPLETED,
                  new AnswerOutcome(
                      null,
                      null,
                      "stop",
                      "gpt-4o-mini",
                      "compare_v1",
                      2100,
                      540,
                      "[]",
                      null,
                      90,
                      210,
                      null,
                      9800,
                      "{\"version_a\":{\"summary\":\"v0.3 요약\",\"citations\":[\"A1\"],"
                          + "\"no_evidence\":false},\"version_b\":{\"summary\":\"v1.x 요약\","
                          + "\"citations\":[\"B1\"],\"no_evidence\":false},\"changes\":[]}"));
              c.recordAnswerEnded(MessageStatus.COMPLETED, T0.plusSeconds(10));
              return c.getId();
            });

    mockMvc
        .perform(detail(userId, conversationId))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.mode").value("COMPARE"))
        .andExpect(jsonPath("$.data.sourceKeyA").value("langchain_v03"))
        .andExpect(jsonPath("$.data.messages[1].content").value(""))
        .andExpect(jsonPath("$.data.messages[1].compareResult.version_a.summary").value("v0.3 요약"))
        .andExpect(jsonPath("$.data.messages[1].compareResult.version_b.citations[0]").value("B1"))
        .andExpect(jsonPath("$.data.messages[1].snapshot.commitShaA").value(SHA))
        .andExpect(jsonPath("$.data.messages[1].snapshot.commitShaB").value(SHA_B))
        .andExpect(jsonPath("$.data.messages[1].snapshot.ingestedAtB").value("2026-10-06"))
        .andExpect(jsonPath("$.data.messages[1].snapshot.versionLabel").doesNotExist())
        .andExpect(jsonPath("$.data.messages[1].sources[0].rankLabel").value("A1"))
        .andExpect(jsonPath("$.data.messages[1].sources[1].rankLabel").value("B1"))
        .andExpect(jsonPath("$.data.messages[1].sources[1].rank").value(1));
  }

  private MockHttpServletRequestBuilder detail(long userId, long conversationId) {
    return get("/api/v1/conversations/" + conversationId).with(user(String.valueOf(userId)));
  }

  /**
   * One completed pair with two sources and one pair still waiting for {@code meta}.
   *
   * @return conversation id, first question id, first answer id
   */
  private long[] answeredConversation(long owner) {
    return tx.execute(
        s -> {
          Conversation c =
              conversations.save(Conversation.single(owner, "Agent 생성", "langchain_v03", T0));
          c.appendMessages(2);
          Message question = messages.save(Message.question(c, owner, "Agent 생성", 1));
          Message answer = messages.save(Message.pendingAnswer(c, owner, "req-detail"));
          answer.applyMeta(
              new AnswerSnapshot(
                  7L,
                  SHA,
                  LocalDate.of(2026, 10, 5),
                  new BigDecimal("0.8732"),
                  "LangChain Agent 생성"),
              false);
          sources.save(source(answer, "1", "0.8732"));
          sources.save(source(answer, "2", "0.7000"));
          answer.finish(
              MessageStatus.COMPLETED,
              new AnswerOutcome(
                  "답변 [1] [2]",
                  null,
                  "stop",
                  "gpt-4o-mini-2024-07-18",
                  "single_v2",
                  1240,
                  312,
                  null,
                  null,
                  80,
                  120,
                  1850,
                  5300));
          c.recordAnswerEnded(MessageStatus.COMPLETED, T0.plusSeconds(5));
          c.appendMessages(2);
          messages.save(Message.question(c, owner, "이어서 질문", 1));
          messages.save(Message.pendingAnswer(c, owner, "req-pending"));
          return new long[] {c.getId(), question.getId(), answer.getId()};
        });
  }

  private static MessageSource source(Message answer, String rankLabel, String similarity) {
    return MessageSource.of(
        answer,
        "langchain_v03",
        rankLabel,
        "Agents > Basic " + rankLabel,
        "https://github.com/langchain-ai/langchain/blob/" + SHA + "/a.md?plain=1#L1-L2",
        null,
        new BigDecimal(similarity));
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
