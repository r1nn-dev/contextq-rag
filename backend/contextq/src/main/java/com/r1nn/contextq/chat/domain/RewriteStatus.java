package com.r1nn.contextq.chat.domain;

/**
 * Multi-turn query rewrite outcome of an ASSISTANT answer (policy §5.2, db-design §3.7).
 *
 * <p>Decided by backend from what it sent and what came back (api-spec §3.1 history 규칙): no history
 * → {@code SKIPPED}; history and a {@code meta.rewrittenQuery} → {@code OK}; history but no
 * rewritten query → {@code FALLBACK}.
 */
public enum RewriteStatus {
  OK,
  FALLBACK,
  SKIPPED
}
