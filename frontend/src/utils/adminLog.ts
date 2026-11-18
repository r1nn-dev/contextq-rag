// Request log line text (api-spec 5.5). No question text exists in the log by design (policy §9.4).

import type { AdminLog } from '@/types/admin'
import { formatNumber } from './format'

/** One-line summary, e.g. "COMPARE · FAILED (LLM_ERROR) · 4.1s · 1,240/312 tokens". */
export function describeLog(log: AdminLog): string {
  const parts = [`${log.mode} · ${log.status}${log.statusReason !== null ? ` (${log.statusReason})` : ''}`]
  if (log.totalMs !== null) parts.push(`${(log.totalMs / 1000).toFixed(1)}s`)
  if (log.promptTokens !== null || log.completionTokens !== null) {
    parts.push(`${formatNumber(log.promptTokens ?? 0)}/${formatNumber(log.completionTokens ?? 0)} tokens`)
  }
  return parts.join(' · ')
}
