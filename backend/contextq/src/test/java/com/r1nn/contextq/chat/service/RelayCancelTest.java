package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.infra.aiserver.AiServerChatClient;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.reactivestreams.Subscription;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import tools.jackson.databind.json.JsonMapper;

/** Client cancel propagates upstream and ends the answer as CLIENT_ABORTED (policy §2.3). */
class RelayCancelTest {

  static final long ANSWER_ID = 305L;
  static final String META =
      "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKey\":\"langchain_v03\",\"ingestRunId\":7,"
          + "\"noContext\":false,\"sources\":[]}";

  private final ChatMessageService messages = mock(ChatMessageService.class);
  private final ChatRelayService relay =
      new ChatRelayService(
          mock(SourceCatalog.class),
          messages,
          mock(AiServerChatClient.class),
          new AiServerProperties(
              "http://unused",
              null,
              Duration.ofSeconds(3),
              Duration.ofSeconds(5),
              Duration.ofSeconds(15),
              Duration.ofSeconds(30),
              Duration.ofSeconds(60)),
          new PersistFailureRegistry(),
          mock(GuestSessionService.class),
          mock(QuestionRateLimiter.class),
          new StreamSlots(),
          new com.r1nn.contextq.global.config.QuotaProperties(10, 100, 2, 1));

  @Test
  void cancelAfterTokenCancelsUpstreamAndStoresPartial() throws Exception {
    AtomicBoolean upstreamCancelled = new AtomicBoolean();
    Flux<ServerSentEvent<String>> upstream =
        Flux.concat(
                Flux.just(data(META), data("{\"event\":\"token\",\"t\":\"부분 \"}")), Flux.never())
            .map(e -> e)
            .doOnCancel(() -> upstreamCancelled.set(true));

    consumeThenCancel(upstream, 2);

    verify(messages, timeout(2000))
        .finish(
            eq(ANSWER_ID),
            eq(MessageStatus.PARTIAL),
            argThat(o -> "CLIENT_ABORTED".equals(o.statusReason()) && "부분 ".equals(o.content())));
    assertThat(upstreamCancelled).isTrue();
  }

  @Test
  void cancelBeforeAnyTokenStoresFailed() throws Exception {
    Flux<ServerSentEvent<String>> upstream = Flux.concat(Flux.just(data(META)), Flux.never());

    consumeThenCancel(upstream, 1);

    verify(messages, timeout(2000))
        .finish(
            eq(ANSWER_ID),
            eq(MessageStatus.FAILED),
            argThat(o -> "CLIENT_ABORTED".equals(o.statusReason())));
  }

  @Test
  void cancelAfterDoneStoresNothingMore() throws Exception {
    Flux<ServerSentEvent<String>> upstream =
        Flux.concat(
            Flux.just(data(META), data("{\"event\":\"done\",\"status\":\"COMPLETED\"}")),
            Flux.never());

    consumeThenCancel(upstream, 2);

    verify(messages, timeout(2000)).finish(eq(ANSWER_ID), eq(MessageStatus.COMPLETED), any());
    verify(messages, never()).finish(anyLong(), eq(MessageStatus.FAILED), argThat(o -> o != null));
    verify(messages).applyMeta(eq(ANSWER_ID), anyString(), any(), anyBoolean(), anyList());
  }

  private void consumeThenCancel(Flux<ServerSentEvent<String>> upstream, int receive)
      throws InterruptedException {
    RelaySession session =
        new RelaySession(
            new MemberAnswerRecorder(messages, new PersistFailureRegistry(), 42L, ANSWER_ID, "r"),
            JsonMapper.builder().build(),
            "r",
            "langchain_v03");
    CountDownLatch received = new CountDownLatch(receive);
    BaseSubscriber<ServerSentEvent<String>> browser =
        new BaseSubscriber<>() {
          @Override
          protected void hookOnSubscribe(Subscription subscription) {
            request(Long.MAX_VALUE);
          }

          @Override
          protected void hookOnNext(ServerSentEvent<String> value) {
            received.countDown();
          }
        };
    relay.relay(upstream, session).subscribe(browser);
    assertThat(received.await(5, TimeUnit.SECONDS)).isTrue();
    browser.cancel();
  }

  private static ServerSentEvent<String> data(String json) {
    return ServerSentEvent.builder(json).build();
  }
}
