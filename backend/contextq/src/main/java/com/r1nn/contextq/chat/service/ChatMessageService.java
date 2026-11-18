package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageRole;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.QuestionTarget;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.QuotaProperties;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Persistence steps of one question (policy §6.3). Each public method is one short transaction; the
 * ai-server call happens between them, outside any transaction.
 *
 * <ol>
 *   <li>{@link #accept}: daily quota under the user row lock, then USER + ASSISTANT(PENDING) in one
 *       transaction, INV-11 under the conversation row lock
 *   <li>{@link #applyMeta}: STREAMING + sources + snapshot (INV-13)
 *   <li>tokens stay in memory (caller)
 *   <li>{@link #finish}: one terminal UPDATE + conversation list fields
 * </ol>
 */
@Service
public class ChatMessageService {

  /** Characters kept per history message sent to ai-server (api-spec §3.1·§6.1). */
  static final int HISTORY_MAX_CHARS = 2000;

  /** USER + ASSISTANT inserted per question. */
  static final int MESSAGES_PER_QUESTION = 2;

  /** Daily quota cost of a single-mode question (policy §8.1). */
  static final int SINGLE_QUOTA_COST = 1;

  private static final Logger log = LoggerFactory.getLogger(ChatMessageService.class);

  private final ConversationRepository conversations;
  private final MessageRepository messages;
  private final MessageSourceRepository sources;
  private final Clock clock;
  private final QuotaProperties quota;

  /** Daily quota resets at 00:00 KST (policy §8.1). */
  static final ZoneId QUOTA_ZONE = ZoneId.of("Asia/Seoul");

  public ChatMessageService(
      ConversationRepository conversations,
      MessageRepository messages,
      MessageSourceRepository sources,
      Clock clock,
      QuotaProperties quota) {
    this.conversations = conversations;
    this.messages = messages;
    this.sources = sources;
    this.clock = clock;
    this.quota = quota;
  }

  /**
   * @param conversationId null for a new conversation
   * @param sourceKey requested version; may be null for an existing conversation
   */
  public record AcceptCommand(
      Long userId, Long conversationId, String question, String sourceKey, String requestId) {}

  /**
   * @param history recent turns for the query rewrite, oldest first ({@code role}, {@code
   *     content}); empty for a new conversation
   */
  public record Accepted(
      Long conversationId,
      Long questionId,
      Long answerId,
      String sourceKey,
      List<Map<String, String>> history) {}

  /** One cited source copied from {@code meta.sources}. */
  public record SourceValue(
      String rankLabel,
      String headingPath,
      String permalink,
      String siteUrl,
      BigDecimal similarity) {}

  /**
   * Versions of the caller's existing conversation, checked before ai-server is called.
   *
   * @param requested mode and versions named by the request; null keys mean "the conversation's"
   * @throws BusinessException {@code CONVERSATION_NOT_FOUND} for missing or foreign conversations
   *     (INV-14), {@code INVALID_REQUEST} when the mode or a named version differs (policy §5.1)
   */
  @Transactional(readOnly = true)
  public QuestionTarget conversationTarget(
      Long userId, Long conversationId, QuestionTarget requested) {
    Conversation c = owned(conversations.findById(conversationId).orElse(null), userId);
    requireSameSetting(c, requested);
    return QuestionTarget.of(c);
  }

  /**
   * Step 1 of policy §6.3. Existing conversations are locked first, so concurrent questions to the
   * same conversation are serialized (INV-11).
   */
  @Transactional
  public Accepted accept(AcceptCommand cmd) {
    requireDailyQuota(cmd.userId(), SINGLE_QUOTA_COST);
    Conversation conversation;
    List<Map<String, String>> history = List.of();
    if (cmd.conversationId() == null) {
      conversation =
          conversations.save(
              Conversation.single(cmd.userId(), cmd.question(), cmd.sourceKey(), clock.instant()));
    } else {
      conversation =
          owned(conversations.findByIdForUpdate(cmd.conversationId()).orElse(null), cmd.userId());
      requireSameSetting(conversation, QuestionTarget.single(cmd.sourceKey()));
      if (!conversation.canAppend(MESSAGES_PER_QUESTION)) {
        throw new BusinessException(ErrorCode.CONVERSATION_FULL);
      }
      if (messages.countInProgress(conversation.getId()) > 0) {
        throw new BusinessException(ErrorCode.CONVERSATION_BUSY);
      }
      history = recentHistory(conversation.getId());
    }
    conversation.appendMessages(MESSAGES_PER_QUESTION);
    Message question =
        messages.save(
            Message.question(conversation, cmd.userId(), cmd.question(), SINGLE_QUOTA_COST));
    Message answer =
        messages.save(
            Message.pendingAnswer(conversation, cmd.userId(), cmd.requestId(), !history.isEmpty()));
    return new Accepted(
        conversation.getId(),
        question.getId(),
        answer.getId(),
        conversation.getSourceKey(),
        history);
  }

  /** Step 2 of policy §6.3: snapshot and sources as values (INV-13). */
  @Transactional
  public void applyMeta(
      Long answerId,
      String sourceKey,
      AnswerSnapshot snapshot,
      boolean noContext,
      List<SourceValue> cited) {
    Message answer = messages.findById(answerId).orElseThrow();
    answer.applyMeta(snapshot, noContext);
    for (SourceValue s : cited) {
      sources.save(
          MessageSource.of(
              answer,
              sourceKey,
              s.rankLabel(),
              s.headingPath(),
              s.permalink(),
              s.siteUrl(),
              s.similarity()));
    }
  }

  /**
   * Step 4 of policy §6.3: the single terminal UPDATE.
   *
   * <p>An already terminal answer is left as is (INV-12; e.g. the sweeper won the race). A status
   * the current state cannot reach (protocol violation) is stored as FAILED.
   *
   * @return the status actually stored
   */
  @Transactional
  public MessageStatus finish(Long answerId, MessageStatus status, AnswerOutcome outcome) {
    Message answer = messages.findByIdForUpdate(answerId).orElseThrow();
    if (answer.getStatus().isTerminal()) {
      log.warn(
          "answer_already_terminal messageId={} stored={} ignored={}",
          answerId,
          answer.getStatus(),
          status);
      return answer.getStatus();
    }
    MessageStatus target = status;
    if (!MessageStatus.canTransition(answer.getStatus(), status)) {
      log.warn(
          "answer_unexpected_terminal messageId={} from={} to={} — stored as FAILED",
          answerId,
          answer.getStatus(),
          status);
      target = MessageStatus.FAILED;
    }
    answer.finish(target, outcome);
    answer.getConversation().recordAnswerEnded(target, clock.instant());
    return target;
  }

  /**
   * Daily limit under the user row lock (policy §8.1): today's USER {@code quota_cost} plus this
   * question must stay within the limit. Runs inside {@link #accept}'s transaction so the insert
   * that follows is covered by the same lock.
   *
   * @throws BusinessException {@code DAILY_QUOTA_EXCEEDED}
   */
  private void requireDailyQuota(Long userId, int cost) {
    messages.lockUserForQuota(userId);
    Instant startOfDay =
        clock.instant().atZone(QUOTA_ZONE).toLocalDate().atStartOfDay(QUOTA_ZONE).toInstant();
    if (messages.sumQuotaCostSince(userId, startOfDay) + cost > quota.daily()) {
      throw new BusinessException(ErrorCode.DAILY_QUOTA_EXCEEDED);
    }
  }

  /**
   * Rewrite context from the DB (policy §5.1·§5.2): the newest 3 turns, oldest first. FAILED and
   * NO_CONTEXT answers are left out while their questions stay; each message is cut to {@link
   * #HISTORY_MAX_CHARS}. Runs under the conversation lock, so no answer is in progress (INV-11).
   */
  private List<Map<String, String>> recentHistory(Long conversationId) {
    List<Message> recent =
        new ArrayList<>(
            messages.findTop6ByConversation_IdOrderByCreatedAtDescIdDesc(conversationId));
    Collections.reverse(recent);
    List<Map<String, String>> history = new ArrayList<>();
    for (Message m : recent) {
      if (m.getRole() == MessageRole.ASSISTANT && !usableAnswer(m)) {
        continue;
      }
      String content = m.getContent();
      if (content.length() > HISTORY_MAX_CHARS) {
        content = content.substring(0, HISTORY_MAX_CHARS);
      }
      history.add(
          Map.of(
              "role", m.getRole() == MessageRole.USER ? "user" : "assistant", "content", content));
    }
    return history;
  }

  /** COMPLETED or PARTIAL answers with text; FAILED and the NO_CONTEXT notice are excluded. */
  private static boolean usableAnswer(Message answer) {
    return (answer.getStatus() == MessageStatus.COMPLETED
            || answer.getStatus() == MessageStatus.PARTIAL)
        && answer.getContent() != null
        && !answer.getContent().isBlank();
  }

  private static Conversation owned(Conversation conversation, Long userId) {
    if (conversation == null || !conversation.isOwnedBy(userId)) {
      throw new BusinessException(ErrorCode.CONVERSATION_NOT_FOUND);
    }
    return conversation;
  }

  /** INV-10: mode and versions are fixed; omitted versions mean the conversation's own. */
  private static void requireSameSetting(Conversation conversation, QuestionTarget requested) {
    if (conversation.getMode() != requested.mode()) {
      throw BusinessException.invalidField("mode", "대화의 모드와 다릅니다.");
    }
    requireSame("sourceKey", requested.sourceKey(), conversation.getSourceKey());
    requireSame("sourceKeyA", requested.sourceKeyA(), conversation.getSourceKeyA());
    requireSame("sourceKeyB", requested.sourceKeyB(), conversation.getSourceKeyB());
  }

  private static void requireSame(String field, String requested, String fixed) {
    if (requested != null && !requested.equals(fixed)) {
      throw BusinessException.invalidField(field, "대화의 버전과 다릅니다.");
    }
  }
}
