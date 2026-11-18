package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.CompareSnapshot;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.service.ChatMessageService.SourceValue;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Logged-in user: the answer is a stored message (policy §6.3). The terminal UPDATE is retried
 * once; when both attempts fail the sweeper stores {@code FAILED(PERSIST_ERROR)} later (§2.3).
 */
final class MemberAnswerRecorder implements AnswerRecorder {

  private static final Logger log = LoggerFactory.getLogger(MemberAnswerRecorder.class);

  private final ChatMessageService messages;
  private final PersistFailureRegistry persistFailures;
  private final Long conversationId;
  private final Long answerId;
  private final String requestId;

  MemberAnswerRecorder(
      ChatMessageService messages,
      PersistFailureRegistry persistFailures,
      Long conversationId,
      Long answerId,
      String requestId) {
    this.messages = messages;
    this.persistFailures = persistFailures;
    this.conversationId = conversationId;
    this.answerId = answerId;
    this.requestId = requestId;
  }

  @Override
  public Long conversationId() {
    return conversationId;
  }

  @Override
  public Long messageId() {
    return answerId;
  }

  @Override
  public void meta(
      String sourceKey, AnswerSnapshot snapshot, boolean noContext, List<SourceValue> cited) {
    messages.applyMeta(answerId, sourceKey, snapshot, noContext, cited);
  }

  @Override
  public void compareMeta(
      String sourceKeyA, String sourceKeyB, CompareSnapshot snapshot, List<SourceValue> cited) {
    messages.applyCompareMeta(answerId, sourceKeyA, sourceKeyB, snapshot, cited);
  }

  @Override
  public void finish(MessageStatus status, AnswerOutcome outcome, boolean refundable) {
    try {
      messages.finish(answerId, status, outcome);
      return;
    } catch (RuntimeException first) {
      log.warn("answer_persist_retry requestId={} messageId={}", requestId, answerId, first);
    }
    try {
      messages.finish(answerId, status, outcome);
    } catch (RuntimeException second) {
      // the browser already has the answer; the sweeper ends the stuck row later
      log.error("answer_persist_failed requestId={} messageId={}", requestId, answerId, second);
      persistFailures.record(answerId, outcome.content());
    }
  }
}
