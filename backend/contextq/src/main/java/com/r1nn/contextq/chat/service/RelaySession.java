package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.AnswerOutcome;
import com.r1nn.contextq.chat.domain.AnswerSnapshot;
import com.r1nn.contextq.chat.domain.MessageStatus;
import com.r1nn.contextq.chat.service.ChatMessageService.SourceValue;
import com.r1nn.contextq.common.error.ErrorCode;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.codec.ServerSentEvent;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * State of one relayed answer (one per request, used by one stream at a time).
 *
 * <p>Methods are synchronized: events arrive on a worker thread while a client cancel arrives on
 * the servlet thread.
 *
 * <p>Turns each ai-server event into the event sent to the browser and hands the steps of policy
 * §6.3 to the {@link AnswerRecorder}: {@code meta} → snapshot, {@code token} → memory only, {@code
 * done}/{@code error}/timeout/disconnect/cancel → one terminal record. A server-side failure before
 * {@code meta} is marked refundable (guest refund, policy §1.3). After the terminal event nothing
 * else is emitted (INV-06).
 */
final class RelaySession {

  private static final Logger log = LoggerFactory.getLogger(RelaySession.class);

  private static final int REWRITTEN_QUERY_MAX = 200;

  private final AnswerRecorder recorder;
  private final ObjectMapper json;
  private final String requestId;
  private final String sourceKey;

  private final StringBuilder content = new StringBuilder();
  private int tokens;
  private boolean metaSeen;
  private volatile boolean anyDataSeen;
  private volatile boolean ended;

  RelaySession(AnswerRecorder recorder, ObjectMapper json, String requestId, String sourceKey) {
    this.recorder = recorder;
    this.json = json;
    this.requestId = requestId;
    this.sourceKey = sourceKey;
  }

  /** Marks the first data event; used by the first-event timeout (heartbeats do not count). */
  boolean observe(ServerSentEvent<String> event) {
    if (event.data() != null) {
      anyDataSeen = true;
    }
    return anyDataSeen;
  }

  boolean isEnded() {
    return ended;
  }

  /** Browser events for one upstream event (empty when nothing is relayed). */
  synchronized List<ServerSentEvent<String>> handle(ServerSentEvent<String> event) {
    if (ended) {
      return List.of();
    }
    if (event.data() == null) {
      return List.of(ServerSentEvent.<String>builder().comment("ping").build());
    }
    JsonNode node = json.readTree(event.data());
    return switch (node.path("event").asString()) {
      case "meta" -> List.of(data(onMeta((ObjectNode) node)));
      case "token" -> {
        content.append(node.path("t").asString());
        tokens++;
        yield List.of(data(event.data()));
      }
      case "done" -> {
        onDone(node);
        yield List.of(data(event.data()));
      }
      case "error" -> List.of(data(onError(node)));
      default -> {
        log.warn("unknown_upstream_event requestId={}", requestId);
        yield List.of();
      }
    };
  }

  /** Stream failed before a terminal event: timeout or broken upstream (api-spec §3.1). */
  synchronized List<ServerSentEvent<String>> fail(Throwable error) {
    if (ended) {
      return List.of();
    }
    if (error instanceof TimeoutException) {
      String reason = anyDataSeen ? "UPSTREAM_IDLE_TIMEOUT" : "UPSTREAM_TIMEOUT";
      return List.of(terminate(ErrorCode.UPSTREAM_TIMEOUT.name(), reason, null));
    }
    log.warn("upstream_stream_failed requestId={}", requestId, error);
    return List.of(terminate(ErrorCode.AI_UNAVAILABLE.name(), "AI_UNAVAILABLE", null));
  }

  /**
   * Browser went away (policy §2.3): the upstream subscription is already being cancelled, which
   * closes the ai-server connection and its OpenAI stream. Store what was received; a client-side
   * cause is never refunded.
   */
  synchronized void onClientCancel() {
    if (ended) {
      return;
    }
    ended = true;
    log.info("stream_aborted requestId={} reason=CLIENT_ABORTED tokens={}", requestId, tokens);
    recorder.finish(
        tokens > 0 ? MessageStatus.PARTIAL : MessageStatus.FAILED,
        AnswerOutcome.interrupted(content.toString(), "CLIENT_ABORTED"),
        false);
  }

  /** Upstream closed without {@code done}/{@code error}. */
  synchronized List<ServerSentEvent<String>> endIfOpen() {
    if (ended) {
      return List.of();
    }
    log.warn("upstream_closed_without_terminal requestId={}", requestId);
    return List.of(terminate(ErrorCode.AI_UNAVAILABLE.name(), "AI_UNAVAILABLE", null));
  }

  private String onMeta(ObjectNode meta) {
    metaSeen = true;
    boolean noContext = meta.path("noContext").asBoolean(false);
    List<SourceValue> cited = new ArrayList<>();
    BigDecimal top1 = null;
    for (JsonNode s : meta.path("sources")) {
      BigDecimal similarity = similarity(s.path("similarity"));
      if (top1 == null) {
        top1 = similarity;
      }
      cited.add(
          new SourceValue(
              s.path("rank").asString(),
              s.path("headingPath").asString(),
              s.path("permalink").asString(),
              s.hasNonNull("siteUrl") ? s.get("siteUrl").asString() : null,
              similarity));
    }
    AnswerSnapshot snapshot =
        new AnswerSnapshot(
            meta.hasNonNull("ingestRunId") ? meta.get("ingestRunId").asLong() : null,
            text(meta, "commitSha"),
            meta.hasNonNull("ingestedAt")
                ? LocalDate.parse(meta.get("ingestedAt").asString())
                : null,
            top1,
            truncate(text(meta, "rewrittenQuery")));
    recorder.meta(sourceKey, snapshot, noContext, cited);
    // client leg adds the stored IDs; both are null for guests (contracts/README.md)
    putId(meta, "conversationId", recorder.conversationId());
    putId(meta, "messageId", recorder.messageId());
    return json.writeValueAsString(meta);
  }

  private void onDone(JsonNode done) {
    ended = true;
    MessageStatus status = MessageStatus.valueOf(done.path("status").asString());
    JsonNode usage = done.path("usage");
    JsonNode latency = done.path("latency");
    AnswerOutcome outcome =
        new AnswerOutcome(
            content.toString(),
            text(done, "statusReason"),
            text(done, "finishReason"),
            text(done, "model"),
            text(done, "promptVersion"),
            integer(usage, "prompt"),
            integer(usage, "completion"),
            done.has("invalidCitations") ? done.get("invalidCitations").toString() : null,
            integer(latency, "rewriteMs"),
            integer(latency, "embedMs"),
            integer(latency, "retrieveMs"),
            integer(latency, "ttftMs"),
            integer(latency, "totalMs"));
    recorder.finish(status, outcome, false); // NO_CONTEXT and completed answers are not refunded
  }

  private String onError(JsonNode error) {
    String upstreamCode = text(error, "code");
    String code = UpstreamCodes.inStream(upstreamCode);
    String message =
        code.equals(upstreamCode) && error.hasNonNull("message")
            ? error.get("message").asString()
            : null;
    return terminateJson(code, upstreamCode == null ? code : upstreamCode, message);
  }

  private ServerSentEvent<String> terminate(String code, String reason, String message) {
    return data(terminateJson(code, reason, message));
  }

  /**
   * Records PARTIAL (tokens ≥ 1) or FAILED and builds the browser {@code error} event. Every caller
   * is a server-side failure, so it is refundable while {@code meta} has not arrived.
   */
  private String terminateJson(String code, String reason, String message) {
    ended = true;
    boolean partial = tokens > 0;
    recorder.finish(
        partial ? MessageStatus.PARTIAL : MessageStatus.FAILED,
        AnswerOutcome.interrupted(content.toString(), reason),
        !metaSeen);
    ObjectNode error = json.createObjectNode();
    error.put("event", "error");
    error.put("code", code);
    error.put("message", message != null ? message : defaultMessage(code));
    error.put("requestId", requestId);
    error.put("partial", partial);
    return json.writeValueAsString(error);
  }

  private static void putId(ObjectNode node, String field, Long id) {
    if (id == null) {
      node.putNull(field);
    } else {
      node.put(field, id);
    }
  }

  private static String defaultMessage(String code) {
    try {
      return ErrorCode.valueOf(code).defaultMessage();
    } catch (IllegalArgumentException e) {
      return ErrorCode.AI_UNAVAILABLE.defaultMessage();
    }
  }

  private static ServerSentEvent<String> data(String payload) {
    return ServerSentEvent.builder(payload).build();
  }

  private static BigDecimal similarity(JsonNode node) {
    return node.isNumber()
        ? node.decimalValue().setScale(4, RoundingMode.HALF_UP)
        : BigDecimal.ZERO;
  }

  private static String text(JsonNode node, String field) {
    return node.hasNonNull(field) ? node.get(field).asString() : null;
  }

  private static Integer integer(JsonNode node, String field) {
    return node.hasNonNull(field) ? node.get(field).asInt() : null;
  }

  private static String truncate(String value) {
    return value == null || value.length() <= REWRITTEN_QUERY_MAX
        ? value
        : value.substring(0, REWRITTEN_QUERY_MAX);
  }
}
