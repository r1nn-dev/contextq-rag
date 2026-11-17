// In-memory conversation store for the mock backend (api-spec 4, policy §6).

import type { ChatMode } from '@/types/chat'
import type {
  AssistantMessage,
  AssistantStatus,
  ConversationDetail,
  ConversationSummary,
  Message,
  SavedSource,
} from '@/types/conversation'
import type { CompareResult, SseSource } from '@/types/sse'
import { answerFixture, findSource, MOCK_SOURCES } from './data'

export interface StoredConversation {
  conversationId: number
  ownerId: number
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
  /** set when the source was disabled, to show the READ_ONLY path */
  sourceDisabled: boolean
  createdAt: string
  updatedAt: string
  messages: Message[]
}

let nextConversationId = 40
let nextMessageId = 300

export const conversations: StoredConversation[] = []

function titleOf(conv: StoredConversation): string {
  const first = conv.messages.find((m) => m.role === 'USER')
  return (first?.content ?? '').replace(/\s+/g, ' ').slice(0, 40)
}

function versionLabelOf(conv: StoredConversation): string {
  if (conv.mode === 'COMPARE') {
    return `${findSource(conv.sourceKeyA)?.versionLabel ?? '?'} vs ${findSource(conv.sourceKeyB)?.versionLabel ?? '?'}`
  }
  return findSource(conv.sourceKey)?.versionLabel ?? '?'
}

function statusOf(conv: StoredConversation): 'OPEN' | 'READ_ONLY' {
  return conv.sourceDisabled || conv.messages.length >= 100 ? 'READ_ONLY' : 'OPEN'
}

export function summaryOf(conv: StoredConversation): ConversationSummary {
  const lastAssistant = [...conv.messages].reverse().find((m): m is AssistantMessage => m.role === 'ASSISTANT')
  return {
    conversationId: conv.conversationId,
    title: titleOf(conv),
    mode: conv.mode,
    sourceKey: conv.sourceKey,
    sourceKeyA: conv.sourceKeyA,
    sourceKeyB: conv.sourceKeyB,
    versionLabel: versionLabelOf(conv),
    messageCount: conv.messages.length,
    lastMessageStatus: lastAssistant?.status ?? null,
    status: statusOf(conv),
    updatedAt: conv.updatedAt,
  }
}

export function detailOf(conv: StoredConversation): ConversationDetail {
  return {
    conversationId: conv.conversationId,
    title: titleOf(conv),
    mode: conv.mode,
    sourceKey: conv.sourceKey,
    sourceKeyA: conv.sourceKeyA,
    sourceKeyB: conv.sourceKeyB,
    status: statusOf(conv),
    messageCount: conv.messages.length,
    createdAt: conv.createdAt,
    updatedAt: conv.updatedAt,
    messages: conv.messages,
  }
}

export function createConversation(
  ownerId: number,
  mode: ChatMode,
  keys: { sourceKey: string | null; sourceKeyA: string | null; sourceKeyB: string | null },
  at = new Date().toISOString(),
): StoredConversation {
  const conv: StoredConversation = {
    conversationId: nextConversationId++,
    ownerId,
    mode,
    ...keys,
    sourceDisabled: false,
    createdAt: at,
    updatedAt: at,
    messages: [],
  }
  conversations.push(conv)
  return conv
}

export interface AssistantRecord {
  status: AssistantStatus
  statusReason: string | null
  content: string
  requestId: string
  sources: SseSource[]
  compareResult?: CompareResult | null
}

/** Appends a USER + ASSISTANT pair and returns the assistant message id. */
export function appendTurn(conv: StoredConversation, question: string, record: AssistantRecord, at = new Date().toISOString()): number {
  conv.messages.push({ messageId: nextMessageId++, role: 'USER', content: question, createdAt: at })
  const source = findSource(conv.sourceKey)
  const a = findSource(conv.sourceKeyA)
  const b = findSource(conv.sourceKeyB)
  const messageId = nextMessageId++
  conv.messages.push({
    messageId,
    role: 'ASSISTANT',
    content: record.content,
    status: record.status,
    statusReason: record.statusReason,
    requestId: record.requestId,
    rewrittenQuery: conv.messages.length > 2 ? `${question} (이전 대화 맥락 반영)` : null,
    snapshot:
      conv.mode === 'COMPARE' && a !== null && b !== null
        ? {
            commitShaA: a.activeRun.commitSha,
            ingestedAtA: a.activeRun.ingestedAt,
            commitShaB: b.activeRun.commitSha,
            ingestedAtB: b.activeRun.ingestedAt,
          }
        : source !== null
          ? { versionLabel: source.versionLabel, commitSha: source.activeRun.commitSha, ingestedAt: source.activeRun.ingestedAt }
          : null,
    usage: record.status === 'NO_CONTEXT' ? null : { prompt: 1240, completion: 312 },
    latency: { rewriteMs: 0, embedMs: 80, retrieveMs: 120, ttftMs: 1500, totalMs: 4800 },
    sources: record.sources.map<SavedSource>((s) => ({ ...s, rankLabel: String(s.rank) })),
    compareResult: record.compareResult ?? null,
    createdAt: at,
    updatedAt: at,
  })
  conv.updatedAt = at
  return messageId
}

// ── seed data for the demo account (user@example.com, userId 2) ──
function hoursAgo(h: number): string {
  return new Date(Date.now() - h * 3_600_000).toISOString()
}

function seedSingle(sourceIndex: number, questions: string[], hours: number, opts: { disabled?: boolean; partialLast?: boolean } = {}): void {
  const sourceKey = MOCK_SOURCES.sources[sourceIndex].sourceKey
  const conv = createConversation(2, 'SINGLE', { sourceKey, sourceKeyA: null, sourceKeyB: null }, hoursAgo(hours))
  const fixture = answerFixture(sourceKey)
  questions.forEach((q, i) => {
    const partial = opts.partialLast === true && i === questions.length - 1
    appendTurn(
      conv,
      q,
      {
        status: partial ? 'PARTIAL' : 'COMPLETED',
        statusReason: partial ? 'CLIENT_CANCELLED' : null,
        content: partial ? fixture.answer.slice(0, 120) : fixture.answer,
        requestId: crypto.randomUUID(),
        sources: fixture.sources,
      },
      hoursAgo(hours - i * 0.1),
    )
  })
  conv.sourceDisabled = opts.disabled === true
}

seedSingle(0, ['ConversationalRetrievalChain을 v1.x로 마이그레이션하는 방법', '메모리는 어떻게 옮기나요?'], 74)
seedSingle(1, ['StreamingStdOutCallbackHandler의 v1.x 대체 방법'], 96, { disabled: true })
seedSingle(0, ['LCEL 체인을 구성하는 기본 방법을 알려줘', 'SequentialChain은 어떻게 써?'], 26, { partialLast: true })
seedSingle(1, ['run()과 invoke() 메서드의 차이가 뭐야?'], 2)
