package com.r1nn.contextq.support;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Function;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

/**
 * Minimal ai-server double on a random local port (reactor-netty, no extra test dependency).
 *
 * <p>Routes answer with a status, content type and a body {@link Flux} so tests can stream SSE
 * frames with delays, hang, or fail. Every request is recorded with its headers and body.
 */
public final class AiServerStub implements AutoCloseable {

  private final Map<String, Function<Recorded, StubResponse>> routes = new ConcurrentHashMap<>();
  private final List<Recorded> requests = new CopyOnWriteArrayList<>();
  private final DisposableServer server;

  public AiServerStub() {
    server =
        HttpServer.create()
            .host("127.0.0.1")
            .port(0)
            .handle(
                (req, res) ->
                    req.receive()
                        .aggregate()
                        .asString(StandardCharsets.UTF_8)
                        .defaultIfEmpty("")
                        .flatMap(
                            body -> {
                              Map<String, String> headers = new ConcurrentHashMap<>();
                              req.requestHeaders()
                                  .forEach(h -> headers.put(h.getKey(), h.getValue()));
                              Recorded recorded =
                                  new Recorded(req.method().name(), req.path(), headers, body);
                              requests.add(recorded);
                              Function<Recorded, StubResponse> route =
                                  routes.get(req.method().name() + " /" + req.path());
                              StubResponse response =
                                  route == null
                                      ? StubResponse.json(404, "{\"code\":\"NOT_FOUND\"}")
                                      : route.apply(recorded);
                              return Mono.delay(response.headerDelay())
                                  .then(
                                      res.status(response.status())
                                          .header("Content-Type", response.contentType())
                                          .sendString(response.body(), StandardCharsets.UTF_8)
                                          .then());
                            }))
            .bindNow();
  }

  public String baseUrl() {
    return "http://127.0.0.1:" + server.port();
  }

  /** Registers a route such as {@code on("GET", "/internal/v1/sources", r -> ...)}. */
  public AiServerStub on(String method, String path, Function<Recorded, StubResponse> handler) {
    routes.put(method + " " + path, handler);
    return this;
  }

  public List<Recorded> requests() {
    return new ArrayList<>(requests);
  }

  public long count(String path) {
    return requests.stream().filter(r -> ("/" + r.path()).equals(path)).count();
  }

  public void reset() {
    routes.clear();
    requests.clear();
  }

  @Override
  public void close() {
    server.disposeNow();
  }

  /** Request as received; header names are case-insensitive in HTTP, lookup via {@link #header}. */
  public record Recorded(String method, String path, Map<String, String> headers, String body) {
    public String header(String name) {
      return headers.entrySet().stream()
          .filter(e -> e.getKey().equalsIgnoreCase(name))
          .map(Map.Entry::getValue)
          .findFirst()
          .orElse(null);
    }
  }

  /** Response definition; {@code body} may emit SSE frames over time. */
  public record StubResponse(
      int status, String contentType, Flux<String> body, Duration headerDelay) {

    public StubResponse(int status, String contentType, Flux<String> body) {
      this(status, contentType, body, Duration.ZERO);
    }

    public static StubResponse json(int status, String json) {
      return new StubResponse(status, "application/json", Flux.just(json));
    }

    /** Same response, but status and headers are sent only after {@code delay}. */
    public StubResponse afterHeaderDelay(Duration delay) {
      return new StubResponse(status, contentType, body, delay);
    }

    /** SSE {@code data:} frame for one JSON event. */
    public static String frame(String json) {
      return "data: " + json + "\n\n";
    }

    /** SSE frames ({@code data: …}) sent one by one with {@code gap} between them. */
    public static StubResponse sse(Duration gap, String... frames) {
      Flux<String> body =
          Flux.fromArray(frames).concatMap(f -> Mono.just(f).delayElement(gap)).map(f -> f);
      return new StubResponse(200, "text/event-stream", body);
    }

    /** SSE frames followed by silence that never ends (the connection stays open). */
    public static StubResponse sseThenHang(String... frames) {
      return new StubResponse(
          200, "text/event-stream", Flux.concat(Flux.fromArray(frames), Flux.never()));
    }
  }
}
