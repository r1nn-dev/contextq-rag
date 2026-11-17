package com.r1nn.contextq.common.error;

import java.util.List;

/**
 * {@code error} object of the failure response (api-spec §0.3 ④·⑤).
 *
 * @param code error code from api-spec §0.4
 * @param message user-facing Korean message (no stack trace or internal host)
 * @param details per-field reasons; empty unless input validation failed
 */
public record ErrorBody(String code, String message, List<FieldReason> details) {

  public ErrorBody {
    details = details == null ? List.of() : List.copyOf(details);
  }

  /** One invalid field (api-spec §0.3 ⑤). */
  public record FieldReason(String field, String reason) {}
}
