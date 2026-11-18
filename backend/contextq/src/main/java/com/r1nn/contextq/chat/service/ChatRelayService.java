package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.QuestionTarget;
import com.r1nn.contextq.chat.dto.ChatStreamRequest;
import com.r1nn.contextq.chat.service.ChatMessageService.AcceptCommand;
import com.r1nn.contextq.chat.service.ChatMessageService.Accepted;
import com.r1nn.contextq.chat.service.GuestSessionService.GuestTicket;
import com.r1nn.contextq.chat.service.StreamSlots.Slot;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.global.config.QuotaProperties;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient.ChatCall;
import com.r1nn.contextq.infra.aiserver.AiServerUnavailableException;
import com.r1nn.contextq.infra.aiserver.UpstreamRejectedException;
import com.r1nn.contextq.infra.aiserver.UpstreamTimeoutException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * Chat relay: browser ⇄ backend ⇄ ai-server SSE (ADR-003 방식 X, api-spec §3.1).
 *
 * <p>Members and guests share the relay; only the {@link AnswerRecorder} differs (stored messages
 * vs. guest usage log and refund). Pre-stream failures throw {@link BusinessException} (plain
 * JSON). Once the stream starts every failure becomes an {@code error} event (INV-09). Not
 * transactional: persistence happens in short transactions, the ai-server call outside them.
 *
 * <p>Compare questions (members only) are processed to the end even when the browser leaves (policy
 * §2.3): the upstream is consumed independently and the browser only watches a replay.
 */
@Service
public class ChatRelayService {

  private static final Logger log = LoggerFactory.getLogger(ChatRelayService.class);
  private static final ObjectMapper JSON = JsonMapper.builder().build();

  private final SourceCatalog sourceCatalog;
  private final ChatMessageService messages;
  private final AiServerChatClient aiServer;
  private final AiServerProperties properties;
  private final PersistFailureRegistry persistFailures;
  private final GuestSessionService guests;
  private final QuestionRateLimiter rateLimiter;
  private final StreamSlots slots;
  private final QuotaProperties quota;

  public ChatRelayService(
      SourceCatalog sourceCatalog,
      ChatMessageService messages,
      AiServerChatClient aiServer,
      AiServerProperties properties,
      PersistFailureRegistry persistFailures,
      GuestSessionService guests,
      QuestionRateLimiter rateLimiter,
      StreamSlots slots,
      QuotaProperties quota) {
    this.sourceCatalog = sourceCatalog;
    this.messages = messages;
    this.aiServer = aiServer;
    this.properties = properties;
    this.persistFailures = persistFailures;
    this.guests = guests;
    this.rateLimiter = rateLimiter;
    this.slots = slots;
    this.quota = quota;
  }

  /** Guest stream plus the {@code Set-Cookie} value of a newly issued session (or null). */
  public record GuestStream(Flux<ServerSentEvent<String>> events, String setCookie) {}

  /**
   * Logged-in user: validates, stores the question and opens the upstream stream. The rewrite
   * history comes from the DB; a {@code history} sent by the client is ignored (policy §5.1).
   *
   * @throws BusinessException pre-stream errors of api-spec §3.1
   */
  public Flux<ServerSentEvent<String>> streamForUser(
      Long userId, ChatStreamRequest request, String requestId) {
    request.requireModeFields();
    rateLimiter.acquire(userId); // 10 per minute (policy §8.1)
    Slot slot = slots.acquire("u:" + userId, quota.concurrentUser());
    try {
      boolean followUp = request.conversationId() != null;
      QuestionTarget target =
          followUp
              ? messages.conversationTarget(
                  userId, request.conversationId(), request.requestedTarget())
              : request.requestedTarget();
      if (target.isCompare()) {
        sourceCatalog.requireComparable(target.sourceKeyA(), target.sourceKeyB(), followUp);
      } else {
        sourceCatalog.requireAskable(target.sourceKey(), followUp);
      }

      String question = request.trimmedQuestion();
      Accepted accepted =
          messages.accept(
              new AcceptCommand(userId, request.conversationId(), question, target, requestId));
      ChatCall call =
          target.isCompare()
              ? ChatCall.compare(
                  requestId, target.sourceKeyA(), target.sourceKeyB(), question, accepted.history())
              : new ChatCall(requestId, target.sourceKey(), question, accepted.history());
      Flux<ServerSentEvent<String>> upstream =
          open(
              call,
              reason ->
                  messages.finish(
                      accepted.answerId(),
                      MessageStatus.FAILED,
                      AnswerOutcome.interrupted(target.isCompare() ? null : "", reason)));
      AnswerRecorder recorder =
          new MemberAnswerRecorder(
              messages, persistFailures, accepted.conversationId(), accepted.answerId(), requestId);
      Flux<ServerSentEvent<String>> events =
          relay(upstream, new RelaySession(recorder, JSON, requestId, target))
              .doFinally(signal -> slot.release());
      if (!target.isCompare()) {
        return events;
      }
      messages.startProcessing(accepted.answerId()); // ai-server accepted: PENDING → PROCESSING
      return detached(events);
    } catch (RuntimeException e) {
      slot.release(); // pre-stream failure: the stream never started
      throw e;
    }
  }

  /**
   * Guest (policy §1.3): single mode only, no stored conversation, one charged question per call.
   *
   * @param rawSid {@code devdocs_sid} cookie value, null on the first question
   * @throws BusinessException {@code GUEST_MODE_NOT_ALLOWED}, guest limits and the pre-stream
   *     errors of api-spec §3.1 (a new session cookie is attached when one was issued)
   */
  public GuestStream streamForGuest(
      String rawSid, String ipAddress, ChatStreamRequest request, String requestId) {
    if (request.mode() == ConversationMode.COMPARE) {
      throw new BusinessException(ErrorCode.GUEST_MODE_NOT_ALLOWED);
    }
    if (request.conversationId() != null) {
      throw BusinessException.invalidField(
          "conversationId", "게스트 대화는 서버에 저장되지 않아 대화 ID를 쓸 수 없습니다.");
    }
    request.requireModeFields();
    String sourceKey = request.sourceKey();
    List<Map<String, String>> history = request.guestHistory();
    sourceCatalog.requireAskable(sourceKey, false);

    GuestTicket ticket = guests.charge(rawSid, ipAddress);
    Slot slot;
    try {
      slot = slots.acquire("g:" + ticket.sidHash(), quota.concurrentGuest());
    } catch (BusinessException e) {
      guests.refund(ticket.sidHash()); // the question was charged but never asked
      throw GuestSessionService.withCookie(e, ticket);
    }
    AnswerRecorder recorder = new GuestAnswerRecorder(guests, ticket.sidHash(), requestId);
    Flux<ServerSentEvent<String>> upstream;
    try {
      upstream =
          open(
              new ChatCall(requestId, sourceKey, request.trimmedQuestion(), history),
              reason ->
                  recorder.finish(
                      MessageStatus.FAILED, AnswerOutcome.interrupted("", reason), true));
    } catch (BusinessException e) {
      slot.release();
      throw GuestSessionService.withCookie(e, ticket);
    }
    return new GuestStream(
        relay(upstream, new RelaySession(recorder, JSON, requestId, sourceKey))
            .doFinally(signal -> slot.release()),
        ticket.setCookie());
  }

  /**
   * Opens ai-server. A failure here ends the answer as FAILED through {@code onFailure} (with the
   * ai-server code as reason) and becomes a JSON error.
   */
  private Flux<ServerSentEvent<String>> open(ChatCall call, Consumer<String> onFailure) {
    try {
      return aiServer.open(call);
    } catch (UpstreamRejectedException e) {
      String reason = e.getCode() != null ? e.getCode() : ErrorCode.AI_UNAVAILABLE.name();
      log.warn(
          "upstream_rejected requestId={} status={} code={}",
          call.requestId(),
          e.getStatus(),
          reason);
      onFailure.accept(reason);
      throw new BusinessException(UpstreamCodes.preStream(e.getCode()));
    } catch (UpstreamTimeoutException e) {
      log.warn("upstream_header_timeout requestId={}", call.requestId());
      onFailure.accept(ErrorCode.UPSTREAM_TIMEOUT.name());
      throw new BusinessException(ErrorCode.UPSTREAM_TIMEOUT);
    } catch (AiServerUnavailableException e) {
      log.warn("upstream_unavailable requestId={}", call.requestId(), e);
      onFailure.accept(ErrorCode.AI_UNAVAILABLE.name());
      throw new BusinessException(ErrorCode.AI_UNAVAILABLE);
    }
  }

  /**
   * Starts consuming {@code events} now and lets the browser watch a replay of them, so a browser
   * cancel does not cancel the processing (policy §2.3 비교 모드 대기 중 이탈). The relay's own timeouts
   * still end a stuck upstream.
   */
  static Flux<ServerSentEvent<String>> detached(Flux<ServerSentEvent<String>> events) {
    return events.replay().autoConnect(0);
  }

  /**
   * Timeouts (policy §2.1): until the first data event the remaining part of the first-event limit
   * applies (heartbeats do not reset it); afterwards every event, heartbeat included, must arrive
   * within the idle limit.
   */
  Flux<ServerSentEvent<String>> relay(
      Flux<ServerSentEvent<String>> upstream, RelaySession session) {
    Duration first = properties.firstEventTimeout();
    Duration idle = properties.idleTimeout();
    long firstDeadline = System.nanoTime() + first.toNanos();
    return upstream
        .timeout(
            Mono.delay(first),
            event ->
                session.observe(event)
                    ? Mono.delay(idle)
                    : Mono.delay(Duration.ofNanos(Math.max(0, firstDeadline - System.nanoTime()))))
        .publishOn(Schedulers.boundedElastic()) // DB writes must not block the Netty event loop
        .concatMapIterable(session::handle)
        .takeUntil(event -> session.isEnded())
        .onErrorResume(error -> Flux.fromIterable(session.fail(error)))
        .concatWith(Flux.defer(() -> Flux.fromIterable(session.endIfOpen())))
        .doOnCancel(session::onClientCancel); // browser gone → upstream cancelled above
  }
}
