package com.r1nn.contextq.chat.controller;

import com.r1nn.contextq.chat.dto.ChatStreamRequest;
import com.r1nn.contextq.chat.service.ChatRelayService;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.common.web.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * {@code POST /api/v1/chat/stream} (api-spec §3.1, ADR-003).
 *
 * <p>Errors thrown before the {@link Flux} is returned are plain JSON responses; after that the
 * stream itself carries {@code error} events (INV-09).
 */
@RestController
@RequestMapping("/api/v1/chat")
public class ChatController {

  private final ChatRelayService relayService;

  public ChatController(ChatRelayService relayService) {
    this.relayService = relayService;
  }

  @PostMapping("/stream")
  public ResponseEntity<Flux<ServerSentEvent<String>>> stream(
      @Valid @RequestBody ChatStreamRequest request,
      Authentication authentication,
      HttpServletRequest httpRequest) {
    Flux<ServerSentEvent<String>> events =
        relayService.streamForUser(userIdOf(authentication), request, requestIdOf(httpRequest));
    return ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .cacheControl(CacheControl.noCache())
        .header("X-Accel-Buffering", "no") // nginx must not buffer SSE (ADR-003)
        .body(events);
  }

  /** The authenticated principal name is the user ID (JWT {@code sub}). */
  static Long userIdOf(Authentication authentication) {
    try {
      return Long.valueOf(authentication.getName());
    } catch (RuntimeException e) {
      throw new BusinessException(ErrorCode.AUTH_TOKEN_INVALID);
    }
  }

  private static String requestIdOf(HttpServletRequest request) {
    Object id = request.getAttribute(RequestIdFilter.ATTRIBUTE);
    return id != null ? id.toString() : RequestIdFilter.currentOrNew();
  }
}
