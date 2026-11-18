package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.repository.MessageRepository;
import com.r1nn.contextq.global.config.ChatSweeperProperties;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Ends answers stuck in STREAMING·PENDING·PROCESSING for 150 s as {@code FAILED(STALE)}, or {@code
 * FAILED(PERSIST_ERROR)} when the relay could not store its terminal update (policy §2.1·§2.3, db-
 * design §5).
 *
 * <p>Each answer goes through {@link ChatMessageService#finish} (row lock, terminal re-check,
 * conversation list fields), so an answer that the relay ended meanwhile is left untouched.
 */
@Component
public class StaleAnswerSweeper {

  private static final Logger log = LoggerFactory.getLogger(StaleAnswerSweeper.class);
  private static final Set<MessageStatus> STUCK =
      Set.of(MessageStatus.STREAMING, MessageStatus.PENDING, MessageStatus.PROCESSING);

  private final MessageRepository messages;
  private final ChatMessageService chatMessages;
  private final PersistFailureRegistry persistFailures;
  private final ChatSweeperProperties properties;
  private final Clock clock;

  public StaleAnswerSweeper(
      MessageRepository messages,
      ChatMessageService chatMessages,
      PersistFailureRegistry persistFailures,
      ChatSweeperProperties properties,
      Clock clock) {
    this.messages = messages;
    this.chatMessages = chatMessages;
    this.persistFailures = persistFailures;
    this.properties = properties;
    this.clock = clock;
  }

  @Scheduled(
      fixedDelayString = "${chat.sweeper.interval:PT60S}",
      initialDelayString = "${chat.sweeper.interval:PT60S}")
  public void scheduledSweep() {
    sweep();
  }

  /**
   * One sweep run.
   *
   * @return number of answers ended by this run
   */
  public int sweep() {
    Instant threshold = clock.instant().minus(properties.staleAfter());
    List<Long> stuck = messages.findStuckAnswerIds(STUCK, threshold);
    int ended = 0;
    for (Long id : stuck) {
      try {
        AnswerOutcome outcome =
            persistFailures
                .consume(id)
                .map(content -> AnswerOutcome.interrupted(content, "PERSIST_ERROR"))
                .orElseGet(() -> AnswerOutcome.interrupted(null, "STALE"));
        if (chatMessages.finish(id, MessageStatus.FAILED, outcome) == MessageStatus.FAILED) {
          ended++;
        }
      } catch (RuntimeException e) {
        log.error("sweeper_failed messageId={}", id, e);
      }
    }
    if (ended > 0) {
      log.warn("stuck_answers_ended count={} threshold={}", ended, threshold);
    }
    return ended;
  }
}
