package com.r1nn.contextq.chat.controller;

import com.r1nn.contextq.chat.dto.SourcesResponse;
import com.r1nn.contextq.chat.dto.SourcesResponse.GuestUsage;
import com.r1nn.contextq.chat.service.GuestCookies;
import com.r1nn.contextq.chat.service.GuestSessionService;
import com.r1nn.contextq.chat.service.GuestSessionService.GuestStatus;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.common.response.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Source metadata for the version picker and guest usage (api-spec §2.1, UI-01). Public. */
@RestController
@RequestMapping("/api/v1/sources")
public class SourceController {

  private final SourceCatalog sourceCatalog;
  private final GuestSessionService guests;

  public SourceController(SourceCatalog sourceCatalog, GuestSessionService guests) {
    this.sourceCatalog = sourceCatalog;
    this.guests = guests;
  }

  /** Catalog (60 s cache) plus the caller's guest usage; never issues a guest cookie. */
  @GetMapping
  public ResponseEntity<ApiResponse<SourcesResponse>> list(
      Authentication authentication,
      @CookieValue(name = GuestCookies.NAME, required = false) String guestSid) {
    SourcesResponse catalog = sourceCatalog.publicSources();
    if (ChatController.isMember(authentication)) {
      return ResponseEntity.ok(ApiResponse.ok(catalog));
    }
    GuestStatus status = guests.status(guestSid);
    return ResponseEntity.ok(
        ApiResponse.ok(
            catalog.withGuest(
                new GuestUsage(
                    status.limit(), status.used(), status.remaining(), status.expiresAt()))));
  }
}
