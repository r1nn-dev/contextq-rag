// Converts a saved conversation (api-spec 4.2) into the same Turn shape the live stream
// produces, so history and new answers render through one component path.

import type { AssistantMessage, ConversationDetail } from '@/types/conversation'
import { isCompareSnapshot } from '@/types/conversation'
import type { Citation, DoneStatus, MetaEvent } from '@/types/sse'
import type { Turn } from './useSseQuery'

const TERMINAL: readonly string[] = ['COMPLETED', 'PARTIAL', 'NO_CONTEXT', 'FAILED']

function rankOf(rank: number | string, rankLabel: string | undefined): Citation {
  // compare answers cite A1/B2; single answers cite integers (policy §5.6)
  if (rankLabel !== undefined && /^[AB]\d+$/.test(rankLabel)) return rankLabel
  return typeof rank === 'number' ? rank : Number(rank)
}

function metaOf(detail: ConversationDetail, m: AssistantMessage): MetaEvent {
  const snapshot = m.snapshot
  const meta: MetaEvent = {
    event: 'meta',
    requestId: m.requestId,
    conversationId: detail.conversationId,
    messageId: m.messageId,
    rewrittenQuery: m.rewrittenQuery,
    noContext: m.status === 'NO_CONTEXT',
    sources: m.sources.map((s) => ({
      rank: rankOf(s.rank, s.rankLabel),
      headingPath: s.headingPath,
      permalink: s.permalink,
      siteUrl: s.siteUrl,
      similarity: s.similarity,
    })),
  }
  if (detail.mode === 'COMPARE' && detail.sourceKeyA !== null && detail.sourceKeyB !== null) {
    meta.sourceKeyA = detail.sourceKeyA
    meta.sourceKeyB = detail.sourceKeyB
    if (isCompareSnapshot(snapshot)) {
      meta.commitShaA = snapshot.commitShaA
      meta.commitShaB = snapshot.commitShaB
      meta.ingestedAtA = snapshot.ingestedAtA
      meta.ingestedAtB = snapshot.ingestedAtB
    }
  } else {
    if (detail.sourceKey !== null) meta.sourceKey = detail.sourceKey
    if (snapshot !== null && !isCompareSnapshot(snapshot)) {
      meta.commitSha = snapshot.commitSha
      meta.ingestedAt = snapshot.ingestedAt
    }
  }
  return meta
}

export function turnsFromDetail(detail: ConversationDetail): Turn[] {
  const turns: Turn[] = []
  let question: string | null = null

  const request = (q: string) => ({
    conversationId: detail.conversationId,
    question: q,
    mode: detail.mode,
    sourceKey: detail.sourceKey,
    sourceKeyA: detail.sourceKeyA,
    sourceKeyB: detail.sourceKeyB,
  })

  for (const m of detail.messages) {
    if (m.role === 'USER') {
      question = m.content
      continue
    }
    const q = question ?? ''
    question = null
    const base = { key: `saved-${m.messageId}`, question: q, request: request(q), meta: metaOf(detail, m), text: m.content }
    if (!TERMINAL.includes(m.status)) {
      // still PENDING / STREAMING / PROCESSING on the server
      turns.push({
        ...base,
        phase: 'failed',
        done: null,
        error: { code: 'IN_PROGRESS', message: '답변을 생성하는 중입니다. 잠시 후 다시 열어주세요.', partial: m.content !== '', retryAfterSec: null },
      })
      continue
    }
    turns.push({
      ...base,
      phase: 'done',
      error: null,
      done: {
        event: 'done',
        status: m.status as DoneStatus,
        statusReason: m.statusReason,
        usage: m.usage,
        latency: m.latency,
        invalidCitations: [],
        compareResult: m.compareResult ?? null,
      },
    })
  }
  if (question !== null) {
    turns.push({
      key: `saved-pending-${detail.conversationId}`,
      question,
      request: request(question),
      phase: 'failed',
      meta: null,
      text: '',
      done: null,
      error: { code: 'IN_PROGRESS', message: '답변이 아직 저장되지 않았습니다.', partial: false, retryAfterSec: null },
    })
  }
  return turns
}
