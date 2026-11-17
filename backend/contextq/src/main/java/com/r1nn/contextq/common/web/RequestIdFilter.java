package com.r1nn.contextq.common.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Request tracing (api-spec §0.1, policy §9.4).
 *
 * <p>Uses the incoming {@code X-Request-Id} when it is a UUID (nginx issues one), otherwise creates
 * a UUID v4. The ID goes to the log context ({@code requestId}), a request attribute and the
 * response header. Runs before Spring Security so 401·403 responses carry it too.
 *
 * <p>The access log line holds method, path, status and duration only — never headers, cookies,
 * query strings or bodies (JWT·cookie·question text stay out of logs).
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

  public static final String HEADER = "X-Request-Id";
  public static final String MDC_KEY = "requestId";
  public static final String ATTRIBUTE = RequestIdFilter.class.getName() + ".requestId";

  private static final Pattern UUID_PATTERN =
      Pattern.compile(
          "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$");
  private static final Logger log = LoggerFactory.getLogger(RequestIdFilter.class);

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    String requestId = resolve(request.getHeader(HEADER));
    long started = System.nanoTime();
    MDC.put(MDC_KEY, requestId);
    request.setAttribute(ATTRIBUTE, requestId);
    response.setHeader(HEADER, requestId);
    try {
      chain.doFilter(request, response);
    } finally {
      log.info(
          "http_request method={} path={} status={} durationMs={}",
          request.getMethod(),
          request.getRequestURI(),
          response.getStatus(),
          (System.nanoTime() - started) / 1_000_000);
      MDC.remove(MDC_KEY);
    }
  }

  /** Request ID of the current request thread, or a new UUID when called outside a request. */
  public static String currentOrNew() {
    String id = MDC.get(MDC_KEY);
    return id != null ? id : UUID.randomUUID().toString();
  }

  static String resolve(String incoming) {
    if (incoming != null && UUID_PATTERN.matcher(incoming).matches()) {
      return incoming.toLowerCase();
    }
    return UUID.randomUUID().toString();
  }
}
