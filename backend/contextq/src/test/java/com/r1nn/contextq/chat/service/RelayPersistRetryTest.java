package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.r1nn.contextq.chat.domain.MessageStatus;
import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import tools.jackson.databind.json.JsonMapper;

/** Terminal UPDATE is retried once; a second failure is left to the sweeper (policy §2.3). */
class RelayPersistRetryTest {

  static final String DONE = "{\"event\":\"done\",\"status\":\"COMPLETED\"}";

  private final ChatMessageService messages = mock(ChatMessageService.class);
  private final PersistFailureRegistry registry = new PersistFailureRegistry();

  @Test
  void secondAttemptSucceeds() {
    when(messages.finish(eq(1L), eq(MessageStatus.COMPLETED), any()))
        .thenThrow(new IllegalStateException("db down"))
        .thenReturn(MessageStatus.COMPLETED);

    session().handle(ServerSentEvent.builder(DONE).build());

    verify(messages, times(2)).finish(eq(1L), eq(MessageStatus.COMPLETED), any());
    assertThat(registry.consume(1L)).isEmpty();
  }

  @Test
  void twoFailuresAreRecordedForTheSweeper() {
    doThrow(new IllegalStateException("db down"))
        .when(messages)
        .finish(eq(1L), eq(MessageStatus.COMPLETED), any());
    RelaySession session = session();
    session.handle(ServerSentEvent.builder("{\"event\":\"token\",\"t\":\"받은 답\"}").build());

    var events = session.handle(ServerSentEvent.builder(DONE).build());

    assertThat(events).hasSize(1); // the browser still gets done
    assertThat(registry.consume(1L)).contains("받은 답");
  }

  private RelaySession session() {
    return new RelaySession(
        messages, registry, JsonMapper.builder().build(), 9L, 1L, "req", "langchain_v03");
  }
}
