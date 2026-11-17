package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.common.error.ErrorCode;
import java.util.Set;

/** ai-server error code → browser error code (api-spec §3.1, policy §9.2). */
final class UpstreamCodes {

  /** Pre-stream codes passed through to the browser as is (api-spec §3.1). */
  private static final Set<String> PASS_THROUGH =
      Set.of(
          "SOURCE_NOT_FOUND",
          "SOURCE_UNAVAILABLE",
          "INDEX_NOT_ACTIVE",
          "AI_BUSY",
          "EMBEDDING_MODEL_MISMATCH");

  /** In-stream codes that reveal internal failures; the browser sees AI_UNAVAILABLE. */
  private static final Set<String> HIDDEN = Set.of("INTERNAL_ERROR", "INTERNAL_UNAUTHORIZED");

  private UpstreamCodes() {}

  static ErrorCode preStream(String upstreamCode) {
    return upstreamCode != null && PASS_THROUGH.contains(upstreamCode)
        ? ErrorCode.valueOf(upstreamCode)
        : ErrorCode.AI_UNAVAILABLE;
  }

  static String inStream(String upstreamCode) {
    if (upstreamCode == null || HIDDEN.contains(upstreamCode)) {
      return ErrorCode.AI_UNAVAILABLE.name();
    }
    return upstreamCode;
  }
}
