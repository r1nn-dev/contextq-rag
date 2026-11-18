package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.CompareSnapshot;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.service.ChatMessageService.SourceValue;
import java.util.List;

/**
 * Where a relayed answer is recorded (policy §6.3). Members store conversation messages; guests
 * store nothing but a usage log and may get a refund (policy §1.3). The relay itself is the same.
 */
interface AnswerRecorder {

  /** Conversation ID for the browser {@code meta}; null for guests (contracts/README.md). */
  Long conversationId();

  /** Answer message ID for the browser {@code meta}; null for guests. */
  Long messageId();

  /** {@code meta} received (policy §6.3 step 2). */
  void meta(String sourceKey, AnswerSnapshot snapshot, boolean noContext, List<SourceValue> cited);

  /**
   * Compare {@code meta} received. Only members ask compare questions (policy §1.3).
   *
   * @param cited sources of both sides ({@code A1…} then {@code B1…})
   */
  default void compareMeta(
      String sourceKeyA, String sourceKeyB, CompareSnapshot snapshot, List<SourceValue> cited) {
    throw new UnsupportedOperationException("compare answers are recorded for members only");
  }

  /**
   * The answer ended (policy §6.3 step 4). Called at most once.
   *
   * @param refundable true when a server-side failure happened before {@code meta} (policy §1.3 환불
   *     규칙)
   */
  void finish(MessageStatus status, AnswerOutcome outcome, boolean refundable);
}
