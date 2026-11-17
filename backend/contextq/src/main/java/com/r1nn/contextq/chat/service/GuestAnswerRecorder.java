package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.service.ChatMessageService.SourceValue;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Guest: no conversation or message is stored (policy §1.3 이력). The end of the answer writes one
 * usage log row and, for a server-side failure before {@code meta}, refunds the question.
 */
final class GuestAnswerRecorder implements AnswerRecorder {

  private static final Logger log = LoggerFactory.getLogger(GuestAnswerRecorder.class);

  private final GuestSessionService guests;
  private final String sidHash;
  private final String requestId;

  GuestAnswerRecorder(GuestSessionService guests, String sidHash, String requestId) {
    this.guests = guests;
    this.sidHash = sidHash;
    this.requestId = requestId;
  }

  @Override
  public Long conversationId() {
    return null;
  }

  @Override
  public Long messageId() {
    return null;
  }

  @Override
  public void meta(
      String sourceKey, AnswerSnapshot snapshot, boolean noContext, List<SourceValue> cited) {
    // guests keep the conversation in the browser only
  }

  @Override
  public void finish(MessageStatus status, AnswerOutcome outcome, boolean refundable) {
    try {
      if (refundable) {
        guests.refund(sidHash);
        log.info("guest_refunded requestId={} reason={}", requestId, outcome.statusReason());
      }
      guests.record(sidHash, status, outcome.promptTokens(), outcome.completionTokens());
    } catch (RuntimeException e) {
      log.error("guest_usage_persist_failed requestId={}", requestId, e);
    }
  }
}
