package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.chat.domain.Conversation;
import com.r1nn.contextq.chat.dto.ConversationSummaryResponse;
import com.r1nn.contextq.chat.repository.ConversationRepository;
import com.r1nn.contextq.common.response.CursorResponse;
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Conversation history of the caller (api-spec §4, policy §6.1). Only the owner's rows are read;
 * there is no admin path to other users' conversations.
 */
@Service
public class ConversationQueryService {

  /** Page size cap of the list (api-spec §4.1). */
  public static final int MAX_PAGE_SIZE = 20;

  private final ConversationRepository conversations;
  private final SourceCatalog sourceCatalog;

  public ConversationQueryService(
      ConversationRepository conversations, SourceCatalog sourceCatalog) {
    this.conversations = conversations;
    this.sourceCatalog = sourceCatalog;
  }

  /**
   * Owner's conversations, newest {@code updated_at} first.
   *
   * <p>One extra row is read to know whether another page exists. The cursor is the last returned
   * row's {@code updatedAt} at full precision, so the strict {@code <} of the next page does not
   * repeat it.
   *
   * @param before cursor; null for the first page
   * @param size 1..{@link #MAX_PAGE_SIZE} (validated by the controller)
   */
  @Transactional(readOnly = true)
  public CursorResponse<ConversationSummaryResponse> list(Long userId, Instant before, int size) {
    Limit limit = Limit.of(size + 1);
    List<Conversation> rows =
        before == null
            ? conversations.findByUserIdOrderByUpdatedAtDescIdDesc(userId, limit)
            : conversations.findByUserIdAndUpdatedAtBeforeOrderByUpdatedAtDescIdDesc(
                userId, before, limit);
    boolean hasNext = rows.size() > size;
    List<Conversation> page = hasNext ? rows.subList(0, size) : rows;
    CatalogView catalog = CatalogView.of(sourceCatalog.currentOrNull());
    List<ConversationSummaryResponse> items =
        page.stream()
            .map(
                c ->
                    ConversationSummaryResponse.from(c, catalog.versionLabel(c), catalog.status(c)))
            .toList();
    String cursor = hasNext ? page.getLast().getUpdatedAt().toString() : null;
    return new CursorResponse<>(items, cursor, hasNext);
  }
}
