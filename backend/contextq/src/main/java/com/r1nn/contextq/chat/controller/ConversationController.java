package com.r1nn.contextq.chat.controller;

import com.r1nn.contextq.chat.dto.ConversationDetailResponse;
import com.r1nn.contextq.chat.dto.ConversationSummaryResponse;
import com.r1nn.contextq.chat.service.ConversationQueryService;
import com.r1nn.contextq.common.response.ApiResponse;
import com.r1nn.contextq.common.response.CursorResponse;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.Instant;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Conversation history (api-spec §4). JWT only: guests keep their conversation in the browser and
 * get 401 from the security chain (api-spec §0.6).
 */
@RestController
@RequestMapping("/api/v1/conversations")
public class ConversationController {

  private final ConversationQueryService queryService;

  public ConversationController(ConversationQueryService queryService) {
    this.queryService = queryService;
  }

  /** Cursor page of the caller's conversations (api-spec §4.1). */
  @GetMapping
  public ResponseEntity<ApiResponse<CursorResponse<ConversationSummaryResponse>>> list(
      Authentication authentication,
      @RequestParam(required = false) Instant before,
      @RequestParam(defaultValue = "20") @Min(1) @Max(ConversationQueryService.MAX_PAGE_SIZE)
          int size) {
    return ResponseEntity.ok(
        ApiResponse.ok(queryService.list(ChatController.userIdOf(authentication), before, size)));
  }

  /** Messages, sources and snapshots of one owned conversation (api-spec §4.2, INV-14). */
  @GetMapping("/{conversationId}")
  public ResponseEntity<ApiResponse<ConversationDetailResponse>> detail(
      Authentication authentication, @PathVariable Long conversationId) {
    return ResponseEntity.ok(
        ApiResponse.ok(
            queryService.detail(ChatController.userIdOf(authentication), conversationId)));
  }
}
