package com.r1nn.contextq.chat.domain;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * ASSISTANT message status and its transition table (policy §10.2, api-spec 부록 C.1).
 *
 * <p>Single mode: PENDING → STREAMING → COMPLETED · PARTIAL · NO_CONTEXT · FAILED. Compare mode:
 * PENDING → PROCESSING → COMPLETED · NO_CONTEXT · FAILED. Terminal states have no outgoing
 * transition (INV-12). Any pair not in the table is rejected.
 */
public enum MessageStatus {
  PENDING,
  STREAMING,
  PROCESSING,
  COMPLETED,
  PARTIAL,
  NO_CONTEXT,
  FAILED;

  private static final Map<MessageStatus, Set<MessageStatus>> ALLOWED =
      Map.of(
          PENDING, EnumSet.of(STREAMING, PROCESSING, NO_CONTEXT, FAILED),
          STREAMING, EnumSet.of(COMPLETED, NO_CONTEXT, PARTIAL, FAILED),
          PROCESSING, EnumSet.of(COMPLETED, NO_CONTEXT, FAILED));

  /** Whether {@code from → to} is a row of policy §10.2. */
  public static boolean canTransition(MessageStatus from, MessageStatus to) {
    if (from == null || to == null) {
      return false;
    }
    return ALLOWED.getOrDefault(from, Set.of()).contains(to);
  }

  /** COMPLETED · PARTIAL · NO_CONTEXT · FAILED (INV-12). */
  public boolean isTerminal() {
    return this == COMPLETED || this == PARTIAL || this == NO_CONTEXT || this == FAILED;
  }

  /** PENDING · STREAMING · PROCESSING — counted by INV-11. */
  public boolean isInProgress() {
    return !isTerminal();
  }

  /** States that INV-11 counts as "in progress". */
  public static Set<MessageStatus> inProgress() {
    return EnumSet.of(PENDING, STREAMING, PROCESSING);
  }
}
