package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.dto.ChatStreamRequest;
import com.r1nn.contextq.chat.service.ChatMessageService.AcceptCommand;
import com.r1nn.contextq.chat.service.ChatMessageService.Accepted;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient.ChatCall;
import com.r1nn.contextq.infra.aiserver.AiServerUnavailableException;
import com.r1nn.contextq.infra.aiserver.UpstreamRejectedException;
import com.r1nn.contextq.infra.aiserver.UpstreamTimeoutException;
import java.time.Duration;
import java.util.List;
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
 * Single-mode relay: browser ⇄ backend ⇄ ai-server SSE (ADR-003 방식 X, api-spec §3.1).
 *
 * <p>Pre-stream failures throw {@link BusinessException} (plain JSON). Once the stream starts every
 * failure becomes an {@code error} event (INV-09). Not transactional: persistence goes through
 * {@link ChatMessageService} in short transactions, the ai-server call runs outside them.
 */
@Service
public class ChatRelayService {

  private static final Logger log = LoggerFactory.getLogger(ChatRelayService.class);
  private static final ObjectMapper JSON = JsonMapper.builder().build();

  private final SourceCatalog sourceCatalog;
  private final ChatMessageService messages;
  private final AiServerChatClient aiServer;
  private final AiServerProperties properties;

  public ChatRelayService(
      SourceCatalog sourceCatalog,
      ChatMessageService messages,
      AiServerChatClient aiServer,
      AiServerProperties properties) {
    this.sourceCatalog = sourceCatalog;
    this.messages = messages;
    this.aiServer = aiServer;
    this.properties = properties;
  }

  /**
   * Validates, stores the question and opens the upstream stream.
   *
   * @throws BusinessException pre-stream errors of api-spec §3.1
   */
  public Flux<ServerSentEvent<String>> streamForUser(
      Long userId, ChatStreamRequest request, String requestId) {
    request.requireSupportedMode();
    boolean followUp = request.conversationId() != null;
    String sourceKey =
        followUp
            ? messages.conversationSource(userId, request.conversationId(), request.sourceKey())
            : request.sourceKey();
    sourceCatalog.requireAskable(sourceKey, followUp);

    String question = request.trimmedQuestion();
    Accepted accepted =
        messages.accept(
            new AcceptCommand(userId, request.conversationId(), question, sourceKey, requestId));
    Flux<ServerSentEvent<String>> upstream =
        open(accepted.answerId(), new ChatCall(requestId, sourceKey, question, List.of()));
    RelaySession session =
        new RelaySession(
            messages, JSON, accepted.conversationId(), accepted.answerId(), requestId, sourceKey);
    return relay(upstream, session);
  }

  /** Opens ai-server; a failure here ends the answer as FAILED and becomes a JSON error. */
  private Flux<ServerSentEvent<String>> open(Long answerId, ChatCall call) {
    try {
      return aiServer.open(call);
    } catch (UpstreamRejectedException e) {
      String reason = e.getCode() != null ? e.getCode() : ErrorCode.AI_UNAVAILABLE.name();
      log.warn(
          "upstream_rejected requestId={} status={} code={}",
          call.requestId(),
          e.getStatus(),
          reason);
      failBeforeStream(answerId, reason);
      throw new BusinessException(UpstreamCodes.preStream(e.getCode()));
    } catch (UpstreamTimeoutException e) {
      log.warn("upstream_header_timeout requestId={}", call.requestId());
      failBeforeStream(answerId, ErrorCode.UPSTREAM_TIMEOUT.name());
      throw new BusinessException(ErrorCode.UPSTREAM_TIMEOUT);
    } catch (AiServerUnavailableException e) {
      log.warn("upstream_unavailable requestId={}", call.requestId(), e);
      failBeforeStream(answerId, ErrorCode.AI_UNAVAILABLE.name());
      throw new BusinessException(ErrorCode.AI_UNAVAILABLE);
    }
  }

  private void failBeforeStream(Long answerId, String reason) {
    messages.finish(answerId, MessageStatus.FAILED, AnswerOutcome.interrupted("", reason));
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
