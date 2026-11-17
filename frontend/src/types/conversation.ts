// docs/specs/api-spec.md > 4. 대화

import type { ChatMode } from './chat'
import type { CompareResult, Latency, Usage } from './sse'

export type ConversationStatus = 'OPEN' | 'READ_ONLY'

export type AssistantStatus =
  | 'PENDING'
  | 'STREAMING'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'PARTIAL'
  | 'NO_CONTEXT'
  | 'FAILED'

export interface ConversationSummary {
  conversationId: number
  title: string
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
  versionLabel: string
  messageCount: number
  lastMessageStatus: AssistantStatus | null
  status: ConversationStatus
  updatedAt: string
}

export interface SavedSource {
  rank: number | string
  rankLabel?: string
  headingPath: string
  permalink: string
  siteUrl: string
  similarity: number
}

export interface SingleSnapshot {
  versionLabel: string
  commitSha: string
  ingestedAt: string
}

export interface CompareSnapshot {
  commitShaA: string
  ingestedAtA: string
  commitShaB: string
  ingestedAtB: string
}

export interface UserMessage {
  messageId: number
  role: 'USER'
  content: string
  createdAt: string
}

export interface AssistantMessage {
  messageId: number
  role: 'ASSISTANT'
  content: string
  status: AssistantStatus
  statusReason: string | null
  requestId: string
  rewrittenQuery: string | null
  snapshot: SingleSnapshot | CompareSnapshot | null
  usage: Usage | null
  latency: Latency | null
  sources: SavedSource[]
  compareResult?: CompareResult | null
  createdAt: string
  updatedAt: string
}

export type Message = UserMessage | AssistantMessage

export interface ConversationDetail {
  conversationId: number
  title: string
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
  status: ConversationStatus
  messageCount: number
  createdAt: string
  updatedAt: string
  messages: Message[]
}

/** Policy §6.1 메시지 상한 */
export const CONVERSATION_MESSAGE_LIMIT = 100

export function isCompareSnapshot(value: SingleSnapshot | CompareSnapshot | null): value is CompareSnapshot {
  return value !== null && 'commitShaA' in value
}
