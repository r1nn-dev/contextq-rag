package com.r1nn.contextq.contract;

import com.networknt.schema.Error;
import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * SSE event contract checker shared by backend contract tests.
 *
 * <p>Event shape: {@code contracts/sse-events.schema.json} (api-spec 부록 B). Stream order: meta →
 * token* → (done | error), meta and the terminal event exactly once (policy INV-06); an error
 * before meta stands alone with partial=false (api-spec 부록 B.1). Mirrors the ai-server checker in
 * {@code ai-server/tests/contract/sse_contract.py}.
 */
final class SseContract {

  /** Stream leg: backend → browser, or ai-server → backend. */
  enum Leg {
    CLIENT("client", "#/$defs/clientEvent"),
    UPSTREAM("upstream", "#/$defs/upstreamEvent");

    final String dir;
    final String entryPoint;

    Leg(String dir, String entryPoint) {
      this.dir = dir;
      this.entryPoint = entryPoint;
    }
  }

  // relative to backend/contextq (Gradle test working directory)
  static final Path CONTRACTS_DIR = Path.of("..", "..", "contracts");

  private static final Set<String> TERMINAL = Set.of("done", "error");
  private static final ObjectMapper MAPPER = JsonMapper.builder().build();
  private static final Map<Leg, Schema> SCHEMAS = loadSchemas();

  private SseContract() {}

  static void validateEvent(JsonNode event, Leg leg) {
    List<Error> errors = SCHEMAS.get(leg).validate(event);
    if (!errors.isEmpty()) {
      String details = errors.stream().map(Error::toString).collect(Collectors.joining("; "));
      throw new ContractViolation(event.path("event").asString() + " 이벤트 스키마 위반: " + details);
    }
  }

  static void validateStream(List<JsonNode> events, Leg leg) {
    if (events.isEmpty()) {
      throw new ContractViolation("빈 스트림: 종결 이벤트가 없습니다");
    }
    events.forEach(event -> validateEvent(event, leg));

    List<String> kinds = events.stream().map(e -> e.get("event").asString()).toList();

    // error before meta: stands alone with partial=false
    if (kinds.getFirst().equals("error")) {
      if (events.size() != 1) {
        throw new ContractViolation("meta 전 error 뒤에는 이벤트가 올 수 없습니다");
      }
      if (events.getFirst().get("partial").booleanValue()) {
        throw new ContractViolation("meta 전 error는 partial=false여야 합니다");
      }
      return;
    }

    if (!kinds.getFirst().equals("meta")) {
      throw new ContractViolation("첫 이벤트는 meta 또는 error여야 합니다: " + kinds.getFirst());
    }
    if (kinds.stream().filter("meta"::equals).count() != 1) {
      throw new ContractViolation("meta는 정확히 1회여야 합니다 (INV-06)");
    }
    if (!TERMINAL.contains(kinds.getLast())) {
      throw new ContractViolation("마지막 이벤트는 done 또는 error여야 합니다: " + kinds.getLast());
    }
    if (kinds.stream().filter(TERMINAL::contains).count() != 1) {
      throw new ContractViolation("종결 이벤트(done|error)는 정확히 1회여야 합니다 (INV-06)");
    }
    List<String> middle = kinds.subList(1, kinds.size() - 1);
    if (middle.stream().anyMatch(kind -> !kind.equals("token"))) {
      throw new ContractViolation("meta와 종결 이벤트 사이에는 token만 올 수 있습니다: " + middle);
    }

    JsonNode meta = events.getFirst();
    JsonNode terminal = events.getLast();
    int tokenCount = middle.size();
    boolean isDone = terminal.get("event").asString().equals("done");

    if (meta.has("sourceKeyA") && tokenCount > 0) {
      throw new ContractViolation("비교 모드는 token 이벤트가 없습니다 (부록 B.2)");
    }
    if (meta.path("noContext").asBoolean(false)) {
      if (tokenCount > 0) {
        throw new ContractViolation("noContext=true 스트림에는 token이 없습니다 (부록 B.1)");
      }
      if (isDone && !terminal.get("status").asString().equals("NO_CONTEXT")) {
        throw new ContractViolation("noContext=true 스트림의 done.status는 NO_CONTEXT여야 합니다");
      }
    }
    if (!isDone && terminal.get("partial").booleanValue() != (tokenCount > 0)) {
      throw new ContractViolation("error.partial은 token 수신 여부와 같아야 합니다");
    }
    if (isDone && terminal.get("status").asString().equals("PARTIAL") && tokenCount == 0) {
      throw new ContractViolation("done.status=PARTIAL은 token 1개 이상 수신 후에만 가능합니다");
    }
  }

  static List<JsonNode> loadExample(Leg leg, String name) {
    JsonNode array = readJson(CONTRACTS_DIR.resolve("examples").resolve(leg.dir).resolve(name));
    List<JsonNode> events = new ArrayList<>();
    array.forEach(events::add);
    return events;
  }

  static List<String> exampleNames(Leg leg) {
    try (Stream<Path> files = Files.list(CONTRACTS_DIR.resolve("examples").resolve(leg.dir))) {
      return files
          .map(path -> path.getFileName().toString())
          .filter(name -> name.endsWith(".json"))
          .sorted()
          .toList();
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  static JsonNode parse(String json) {
    return MAPPER.readTree(json);
  }

  private static Map<Leg, Schema> loadSchemas() {
    JsonNode root = readJson(CONTRACTS_DIR.resolve("sse-events.schema.json"));
    SchemaRegistry registry = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12);
    Map<Leg, Schema> schemas = new EnumMap<>(Leg.class);
    for (Leg leg : Leg.values()) {
      // same schema, different entry point
      ObjectNode entry = (ObjectNode) root.deepCopy();
      entry.put("$ref", leg.entryPoint);
      schemas.put(leg, registry.getSchema(entry.toString(), InputFormat.JSON));
    }
    return schemas;
  }

  private static JsonNode readJson(Path path) {
    try {
      return MAPPER.readTree(Files.readString(path));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /** Schema or ordering rule violation. */
  static final class ContractViolation extends AssertionError {
    ContractViolation(String message) {
      super(message);
    }
  }
}
