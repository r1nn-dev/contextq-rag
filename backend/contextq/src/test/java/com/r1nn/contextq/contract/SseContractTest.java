package com.r1nn.contextq.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.contract.SseContract.ContractViolation;
import com.r1nn.contextq.contract.SseContract.Leg;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** backend side of the SSE contract: same schema and examples as the ai-server contract tests. */
class SseContractTest {

  static Stream<Arguments> examples() {
    return Stream.of(Leg.values())
        .flatMap(
            leg -> SseContract.exampleNames(leg).stream().map(name -> Arguments.of(leg, name)));
  }

  @ParameterizedTest(name = "{0} {1}")
  @MethodSource("examples")
  void contractExamplesAreValid(Leg leg, String name) {
    assertThatCode(() -> SseContract.validateStream(SseContract.loadExample(leg, name), leg))
        .doesNotThrowAnyException();
  }

  @Test
  void bothLegsHaveExamples() {
    assertThat(SseContract.exampleNames(Leg.CLIENT)).isNotEmpty();
    assertThat(SseContract.exampleNames(Leg.UPSTREAM)).isNotEmpty();
  }

  // --- schema violations ---

  @Test
  void snakeCaseFieldIsRejected() {
    JsonNode event =
        SseContract.parse(
            """
            {"event":"error","code":"LLM_ERROR","message":"m","request_id":"r","partial":false}
            """);
    assertThatThrownBy(() -> SseContract.validateEvent(event, Leg.CLIENT))
        .isInstanceOf(ContractViolation.class)
        .hasMessageContaining("스키마 위반");
  }

  @Test
  void clientMetaRequiresConversationAndMessageIds() {
    JsonNode upstreamMeta = single(Leg.UPSTREAM).getFirst();
    assertThatThrownBy(() -> SseContract.validateEvent(upstreamMeta, Leg.CLIENT))
        .isInstanceOf(ContractViolation.class);
  }

  @Test
  void upstreamMetaRejectsConversationId() {
    JsonNode clientMeta = single(Leg.CLIENT).getFirst();
    assertThatThrownBy(() -> SseContract.validateEvent(clientMeta, Leg.UPSTREAM))
        .isInstanceOf(ContractViolation.class);
  }

  @Test
  void unknownDoneStatusIsRejected() {
    List<JsonNode> events = single(Leg.CLIENT);
    ((ObjectNode) events.getLast()).put("status", "OK");
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .isInstanceOf(ContractViolation.class);
  }

  // --- ordering violations (INV-06) ---

  @Test
  void emptyStreamIsRejected() {
    assertThatThrownBy(() -> SseContract.validateStream(List.of(), Leg.CLIENT))
        .hasMessageContaining("빈 스트림");
  }

  @Test
  void tokenBeforeMetaIsRejected() {
    List<JsonNode> events = single(Leg.CLIENT);
    events.addFirst(events.remove(1));
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("첫 이벤트");
  }

  @Test
  void duplicateMetaIsRejected() {
    List<JsonNode> events = single(Leg.CLIENT);
    events.add(1, events.getFirst().deepCopy());
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("meta는 정확히 1회");
  }

  @Test
  void missingTerminalIsRejected() {
    List<JsonNode> events = single(Leg.CLIENT);
    events.removeLast();
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("마지막 이벤트");
  }

  @Test
  void preMetaErrorMustNotBePartial() {
    List<JsonNode> events = example(Leg.CLIENT, "error-before-meta.json");
    ((ObjectNode) events.getFirst()).put("partial", true);
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("partial=false");
  }

  @Test
  void errorPartialMustMatchTokenPresence() {
    List<JsonNode> events = example(Leg.CLIENT, "error-midstream.json");
    ((ObjectNode) events.getLast()).put("partial", false);
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("partial");
  }

  @Test
  void compareStreamHasNoTokens() {
    List<JsonNode> events = example(Leg.CLIENT, "compare-completed.json");
    events.add(1, SseContract.parse("{\"event\":\"token\",\"t\":\"x\"}"));
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("비교 모드");
  }

  @Test
  void noContextStreamEndsWithNoContextStatus() {
    List<JsonNode> events = example(Leg.CLIENT, "single-no-context.json");
    ((ObjectNode) events.getLast()).put("status", "COMPLETED");
    assertThatThrownBy(() -> SseContract.validateStream(events, Leg.CLIENT))
        .hasMessageContaining("NO_CONTEXT");
  }

  private static List<JsonNode> single(Leg leg) {
    return example(leg, "single-completed.json");
  }

  // mutable deep copy so each test can tamper with events
  private static List<JsonNode> example(Leg leg, String name) {
    List<JsonNode> copy = new ArrayList<>();
    SseContract.loadExample(leg, name).forEach(event -> copy.add(event.deepCopy()));
    return copy;
  }
}
