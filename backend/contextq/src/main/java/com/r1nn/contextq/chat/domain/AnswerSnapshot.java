package com.r1nn.contextq.chat.domain;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Retrieval snapshot copied from the {@code meta} event (INV-13, policy §6.3 step 2).
 *
 * @param ingestRunId ACTIVE run used for the answer
 * @param commitSha collected commit SHA (40 chars)
 * @param ingestedAt collection date (UTC)
 * @param top1Similarity similarity of rank 1, null when no source was returned
 * @param rewrittenQuery query used for retrieval; null when not rewritten
 */
public record AnswerSnapshot(
    Long ingestRunId,
    String commitSha,
    LocalDate ingestedAt,
    BigDecimal top1Similarity,
    String rewrittenQuery) {}
