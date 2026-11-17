package com.r1nn.contextq.chat.domain;

import static com.r1nn.contextq.chat.domain.MessageStatus.COMPLETED;
import static com.r1nn.contextq.chat.domain.MessageStatus.FAILED;
import static com.r1nn.contextq.chat.domain.MessageStatus.NO_CONTEXT;
import static com.r1nn.contextq.chat.domain.MessageStatus.PARTIAL;
import static com.r1nn.contextq.chat.domain.MessageStatus.PENDING;
import static com.r1nn.contextq.chat.domain.MessageStatus.PROCESSING;
import static com.r1nn.contextq.chat.domain.MessageStatus.STREAMING;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

/** Every one of the 49 status pairs against policy §10.2 (INV-12, db-design §5). */
class MessageStatusTest {

  /** Rows of policy §10.2 (From → To). Everything else must be rejected. */
  static final Set<String> POLICY_ROWS =
      Set.of(
          "PENDING>STREAMING",
          "PENDING>PROCESSING",
          "PENDING>NO_CONTEXT",
          "PENDING>FAILED",
          "STREAMING>COMPLETED",
          "STREAMING>NO_CONTEXT",
          "STREAMING>PARTIAL",
          "STREAMING>FAILED",
          "PROCESSING>COMPLETED",
          "PROCESSING>NO_CONTEXT",
          "PROCESSING>FAILED");

  static Stream<Arguments> allPairs() {
    return Stream.of(MessageStatus.values())
        .flatMap(from -> Stream.of(MessageStatus.values()).map(to -> Arguments.of(from, to)));
  }

  @ParameterizedTest(name = "{0} -> {1}")
  @MethodSource("allPairs")
  void matchesPolicyTable(MessageStatus from, MessageStatus to) {
    boolean expected = POLICY_ROWS.contains(from + ">" + to);

    assertThat(MessageStatus.canTransition(from, to)).isEqualTo(expected);
  }

  @Test
  void terminalStatesHaveNoOutgoingTransition() {
    for (MessageStatus terminal : new MessageStatus[] {COMPLETED, PARTIAL, NO_CONTEXT, FAILED}) {
      assertThat(terminal.isTerminal()).isTrue();
      for (MessageStatus to : MessageStatus.values()) {
        assertThat(MessageStatus.canTransition(terminal, to)).as(terminal + "->" + to).isFalse();
      }
    }
  }

  @Test
  void inProgressStatesAreCountedByInv11() {
    assertThat(MessageStatus.inProgress())
        .containsExactlyInAnyOrder(PENDING, STREAMING, PROCESSING);
    assertThat(PENDING.isInProgress()).isTrue();
    assertThat(FAILED.isInProgress()).isFalse();
  }

  @Test
  void nullIsNeverAllowed() {
    assertThat(MessageStatus.canTransition(null, PENDING)).isFalse();
    assertThat(MessageStatus.canTransition(PENDING, null)).isFalse();
  }
}
