package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.domain.ConversationMode;
import com.r1nn.contextq.chat.domain.ConversationStatus;
import com.r1nn.contextq.infra.aiserver.InternalSources;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Version labels and activity of the catalog sources for one history request (api-spec §4.1 조회 규칙).
 *
 * <p>Without a catalog (ai-server down, nothing cached) every source counts as active and the label
 * falls back to the source key, so history stays readable; a follow-up question is checked again
 * when it is asked.
 */
final class CatalogView {

  private final Map<String, InternalSources.Source> sources;

  private CatalogView(Map<String, InternalSources.Source> sources) {
    this.sources = sources;
  }

  /**
   * @param catalog null when unavailable
   */
  static CatalogView of(InternalSources catalog) {
    if (catalog == null) {
      return new CatalogView(null);
    }
    return new CatalogView(
        catalog.sources().stream()
            .collect(
                Collectors.toMap(
                    InternalSources.Source::sourceKey, Function.identity(), (a, b) -> a)));
  }

  /** SINGLE: the source label; COMPARE: {@code "v0.3 vs v1.x"} (api-spec §4.1). */
  String versionLabel(Conversation c) {
    if (c.getMode() == ConversationMode.COMPARE) {
      return label(c.getSourceKeyA()) + " vs " + label(c.getSourceKeyB());
    }
    return label(c.getSourceKey());
  }

  /** READ_ONLY when full or any source of the conversation is inactive (db-design §3.6). */
  ConversationStatus status(Conversation c) {
    boolean sourcesActive =
        c.getMode() == ConversationMode.COMPARE
            ? active(c.getSourceKeyA()) && active(c.getSourceKeyB())
            : active(c.getSourceKey());
    return c.isFull() || !sourcesActive ? ConversationStatus.READ_ONLY : ConversationStatus.OPEN;
  }

  /** Catalog label of the source; the key itself when unknown or unavailable. */
  String label(String sourceKey) {
    if (sources == null) {
      return sourceKey;
    }
    InternalSources.Source source = sources.get(sourceKey);
    return source != null ? source.versionLabel() : sourceKey;
  }

  /** Enabled AND an ACTIVE run (policy §3.2); a key missing from the catalog is inactive. */
  private boolean active(String sourceKey) {
    if (sources == null) {
      return true;
    }
    InternalSources.Source source = sources.get(sourceKey);
    return source != null && source.active();
  }
}
