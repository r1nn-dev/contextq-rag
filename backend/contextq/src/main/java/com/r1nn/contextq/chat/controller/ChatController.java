package com.r1nn.contextq.chat.controller;

import com.r1nn.contextq.chat.dto.ChatStreamRequest;
import com.r1nn.contextq.chat.service.ChatRelayService;
import com.r1nn.contextq.chat.service.ChatRelayService.GuestStream;
import com.r1nn.contextq.chat.service.GuestCookies;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.common.web.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * {@code POST /api/v1/chat/stream} (api-spec §3.1, ADR-003).
 *
 * <p>A valid Access Token makes the caller a member even when a guest cookie is present (policy
 * §1.3); otherwise the caller is a guest. Errors thrown before the {@link Flux} is returned are
 * plain JSON responses; after that the stream itself carries {@code error} events (INV-09).
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
      @CookieValue(name = GuestCookies.NAME, required = false) String guestSid,
      HttpServletRequest httpRequest) {
    String requestId = requestIdOf(httpRequest);
    ResponseEntity.BodyBuilder response =
        ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noCache())
            .header("X-Accel-Buffering", "no"); // nginx must not buffer SSE (ADR-003)
    if (isMember(authentication)) {
      return response.body(
          relayService.streamForUser(userIdOf(authentication), request, requestId));
    }
    GuestStream guest =
        relayService.streamForGuest(guestSid, httpRequest.getRemoteAddr(), request, requestId);
    if (guest.setCookie() != null) {
      response.header(HttpHeaders.SET_COOKIE, guest.setCookie());
    }
    return response.body(guest.events());
  }

  static boolean isMember(Authentication authentication) {
    return authentication != null
        && authentication.isAuthenticated()
        && !(authentication instanceof AnonymousAuthenticationToken);
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
