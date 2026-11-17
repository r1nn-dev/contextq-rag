package com.r1nn.contextq.chat.controller;

import com.r1nn.contextq.chat.dto.SourcesResponse;
import com.r1nn.contextq.chat.service.SourceCatalog;
import com.r1nn.contextq.common.response.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Source metadata for the version picker (api-spec §2.1, UI-01). Public. */
@RestController
@RequestMapping("/api/v1/sources")
public class SourceController {

  private final SourceCatalog sourceCatalog;

  public SourceController(SourceCatalog sourceCatalog) {
    this.sourceCatalog = sourceCatalog;
  }

  @GetMapping
  public ResponseEntity<ApiResponse<SourcesResponse>> list() {
    return ResponseEntity.ok(ApiResponse.ok(sourceCatalog.publicSources()));
  }
}
