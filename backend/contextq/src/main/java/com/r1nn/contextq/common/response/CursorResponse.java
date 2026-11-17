package com.r1nn.contextq.common.response;

import java.util.List;

/**
 * Cursor page for list APIs (api-spec §0.3 ③).
 *
 * @param items page items
 * @param cursor ISO 8601 value for the next {@code before} parameter; null on the last page
 * @param hasNext whether another page exists
 */
public record CursorResponse<T>(List<T> items, String cursor, boolean hasNext) {

  public CursorResponse {
    items = List.copyOf(items);
  }
}
