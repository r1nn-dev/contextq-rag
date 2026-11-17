package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.Message;
import com.r1nn.contextq.chat.domain.MessageSource;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.chat.repository.MessageSourceRepository;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import java.math.BigDecimal;
import java.time.Clock;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Persistence steps of one question (policy §6.3). Each public method is one short transaction; the
 * ai-server call happens between them, outside any transaction.
 *
 * <ol>
 *   <li>{@link #accept}: USER + ASSISTANT(PENDING) in one transaction, INV-11 under the
 *       conversation row lock
 *   <li>{@link #applyMeta}: STREAMING + sources + snapshot (INV-13)
 *   <li>tokens stay in memory (caller)
 *   <li>{@link #finish}: one terminal UPDATE + conversation list fields
 * </ol>
 */
@Service
public class ChatMessageService {

  /** USER + ASSISTANT inserted per question. */
  static final int MESSAGES_PER_QUESTION = 2;

  /** Daily quota cost of a single-mode question (policy §8.1). */
  static final int SINGLE_QUOTA_COST = 1;

  private static final Logger log = LoggerFactory.getLogger(ChatMessageService.class);

  private final ConversationRepository conversations;
  private final MessageRepository messages;
  private final MessageSourceRepository sources;
  private final Clock clock;

  public ChatMessageService(
      ConversationRepository conversations,
      MessageRepository messages,
      MessageSourceRepository sources,
      Clock clock) {
    this.conversations = conversations;
    this.messages = messages;
    this.sources = sources;
    this.clock = clock;
  }

  /**
   * @param conversationId null for a new conversation
   * @param sourceKey requested version; may be null for an existing conversation
   */
  public record AcceptCommand(
      Long userId, Long conversationId, String question, String sourceKey, String requestId) {}

  public record Accepted(Long conversationId, Long questionId, Long answerId, String sourceKey) {}

  /** One cited source copied from {@code meta.sources}. */
  public record SourceValue(
      String rankLabel,
      String headingPath,
      String permalink,
      String siteUrl,
      BigDecimal similarity) {}

  /**
   * Source key of the caller's existing SINGLE conversation, checked before ai-server is called.
   *
   * @throws BusinessException {@code CONVERSATION_NOT_FOUND} for missing or foreign conversations
   *     (INV-14), {@code INVALID_REQUEST} when the conversation is not SINGLE or the requested
   *     version differs (policy §5.1)
   */
  @Transactional(readOnly = true)
  public String conversationSource(Long userId, Long conversationId, String requestedSourceKey) {
    Conversation c = owned(conversations.findById(conversationId).orElse(null), userId);
    requireSameSetting(c, requestedSourceKey);
    return c.getSourceKey();
  }

  /**
   * Step 1 of policy §6.3. Existing conversations are locked first, so concurrent questions to the
   * same conversation are serialized (INV-11).
   */
  @Transactional
  public Accepted accept(AcceptCommand cmd) {
    Conversation conversation;
    if (cmd.conversationId() == null) {
      conversation =
          conversations.save(
              Conversation.single(cmd.userId(), cmd.question(), cmd.sourceKey(), clock.instant()));
    } else {
      conversation =
          owned(conversations.findByIdForUpdate(cmd.conversationId()).orElse(null), cmd.userId());
      requireSameSetting(conversation, cmd.sourceKey());
      if (!conversation.canAppend(MESSAGES_PER_QUESTION)) {
        throw new BusinessException(ErrorCode.CONVERSATION_FULL);
      }
      if (messages.countInProgress(conversation.getId()) > 0) {
        throw new BusinessException(ErrorCode.CONVERSATION_BUSY);
      }
    }
    conversation.appendMessages(MESSAGES_PER_QUESTION);
    Message question =
        messages.save(
            Message.question(conversation, cmd.userId(), cmd.question(), SINGLE_QUOTA_COST));
    Message answer =
        messages.save(Message.pendingAnswer(conversation, cmd.userId(), cmd.requestId()));
    return new Accepted(
        conversation.getId(), question.getId(), answer.getId(), conversation.getSourceKey());
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
    Message answer = messages.findById(answerId).orElseThrow();
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

  private static Conversation owned(Conversation conversation, Long userId) {
    if (conversation == null || !conversation.isOwnedBy(userId)) {
      throw new BusinessException(ErrorCode.CONVERSATION_NOT_FOUND);
    }
    return conversation;
  }

  private static void requireSameSetting(Conversation conversation, String requestedSourceKey) {
    if (conversation.getMode() != ConversationMode.SINGLE) {
      throw BusinessException.invalidField("mode", "대화의 모드와 다릅니다.");
    }
    if (requestedSourceKey != null && !requestedSourceKey.equals(conversation.getSourceKey())) {
      throw BusinessException.invalidField("sourceKey", "대화의 버전과 다릅니다.");
    }
  }
}
