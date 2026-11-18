package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.domain.QuestionTarget;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.global.config.QuotaProperties;
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
import reactor.core.publisher.Mono;
import tools.jackson.databind.json.JsonMapper;

/**
 * A browser leaving a compare answer does not stop it; the result is still stored (policy §2.3).
 */
class CompareDetachTest {

  static final long ANSWER_ID = 501L;
  static final String META =
      "{\"event\":\"meta\",\"requestId\":\"r\",\"sourceKeyA\":\"langchain_v03\","
          + "\"sourceKeyB\":\"langchain_v1x\",\"ingestRunIdA\":7,\"ingestRunIdB\":8,"
          + "\"noContext\":false,\"sources\":[{\"rank\":\"A1\",\"headingPath\":\"h\","
          + "\"permalink\":\"https://p\",\"siteUrl\":\"https://s\",\"similarity\":0.8}]}";
  static final String DONE =
      "{\"event\":\"done\",\"status\":\"COMPLETED\",\"compareResult\":{\"version_a\":"
          + "{\"summary\":\"a\",\"citations\":[\"A1\"],\"no_evidence\":false},\"version_b\":"
          + "{\"summary\":\"\",\"citations\":[],\"no_evidence\":true},\"changes\":[]}}";

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
          new QuotaProperties(10, 100, 2, 1));

  @Test
  void browserCancelAfterMetaStillStoresTheResult() throws Exception {
    AtomicBoolean processingEnded = new AtomicBoolean();
    Flux<ServerSentEvent<String>> upstream =
        Flux.concat(
            Flux.just(data(META)),
            Mono.just(data(DONE)).delayElement(Duration.ofMillis(300)),
            Flux.<ServerSentEvent<String>>never());
    RelaySession session =
        new RelaySession(
            new MemberAnswerRecorder(messages, new PersistFailureRegistry(), 42L, ANSWER_ID, "r"),
            JsonMapper.builder().build(),
            "r",
            QuestionTarget.compare("langchain_v03", "langchain_v1x"));

    Flux<ServerSentEvent<String>> browserView =
        ChatRelayService.detached(
            relay.relay(upstream, session).doFinally(s -> processingEnded.set(true)));
    CountDownLatch metaSeen = new CountDownLatch(1);
    BaseSubscriber<ServerSentEvent<String>> browser =
        new BaseSubscriber<>() {
          @Override
          protected void hookOnSubscribe(Subscription subscription) {
            request(Long.MAX_VALUE);
          }

          @Override
          protected void hookOnNext(ServerSentEvent<String> value) {
            metaSeen.countDown();
          }
        };
    browserView.subscribe(browser);
    assertThat(metaSeen.await(5, TimeUnit.SECONDS)).isTrue();
    browser.cancel(); // the browser leaves before the result

    verify(messages, timeout(3000))
        .finish(
            eq(ANSWER_ID),
            eq(MessageStatus.COMPLETED),
            argThat(o -> o.content() == null && o.compareResultJson().contains("version_a")));
    verify(messages)
        .applyCompareMeta(
            eq(ANSWER_ID), eq("langchain_v03"), eq("langchain_v1x"), any(), anyList());
    verify(messages, never()).finish(eq(ANSWER_ID), eq(MessageStatus.FAILED), any());
    assertThat(processingEnded).isTrue(); // the slot is returned when processing ends
  }

  private static ServerSentEvent<String> data(String json) {
    return ServerSentEvent.builder(json).build();
  }
}
