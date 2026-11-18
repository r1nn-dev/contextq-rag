package com.r1nn.contextq.chat.domain;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Compare-mode retrieval snapshot copied from the {@code meta} event (INV-13, api-spec 부록 B.4).
 *
 * @param top1SimilarityA similarity of A1, null when side A had no source (no evidence)
 * @param top1SimilarityB similarity of B1, null when side B had no source
 * @param rewrittenQuery query used for both searches; null when not rewritten
 */
public record CompareSnapshot(
    Long ingestRunIdA,
    Long ingestRunIdB,
    String commitShaA,
    String commitShaB,
    LocalDate ingestedAtA,
    LocalDate ingestedAtB,
    BigDecimal top1SimilarityA,
    BigDecimal top1SimilarityB,
    String rewrittenQuery) {}
