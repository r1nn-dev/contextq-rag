// Client-leg SSE events (contracts/sse-events.schema.json > $defs/clientEvent)

import { isRecord } from './api'

/** Single mode ranks are integers; compare mode ranks are A1.. / B1.. (policy §5.6). */
export type Citation = number | string

export interface SseSource {
  rank: Citation
  headingPath: string
  permalink: string
  siteUrl: string
  similarity: number
}

export interface MetaEvent {
  event: 'meta'
  requestId: string
  conversationId: number | null
  messageId: number | null
  sourceKey?: string
  ingestRunId?: number
  commitSha?: string
  ingestedAt?: string
  sourceKeyA?: string
  sourceKeyB?: string
  ingestRunIdA?: number
  ingestRunIdB?: number
  commitShaA?: string
  commitShaB?: string
  ingestedAtA?: string
  ingestedAtB?: string
  rewrittenQuery?: string | null
  noContext?: boolean
  sources?: SseSource[]
}

export interface TokenEvent {
  event: 'token'
  t: string
}

export type DoneStatus = 'COMPLETED' | 'PARTIAL' | 'NO_CONTEXT' | 'FAILED'

export interface Usage {
  prompt: number
  completion: number
}

export interface Latency {
  rewriteMs?: number | null
  embedMs?: number | null
  retrieveMs?: number | null
  ttftMs?: number | null
  totalMs?: number | null
}

export interface CompareSide {
  summary: string
  citations: Citation[]
  no_evidence: boolean
}

export interface CompareChange {
  aspect: string
  a: string
  b: string
  citations_a: string[]
  citations_b: string[]
}

/** Inner keys stay snake_case (policy §9.3). */
export interface CompareResult {
  version_a: CompareSide
  version_b: CompareSide
  changes: CompareChange[]
}

export interface DoneEvent {
  event: 'done'
  status: DoneStatus
  statusReason?: string | null
  finishReason?: string | null
  usage?: Usage | null
  latency?: Latency | null
  invalidCitations?: Citation[]
  compareResult?: CompareResult | null
}

export interface ErrorEvent {
  event: 'error'
  code: string
  message: string
  requestId: string
  partial: boolean
}

export type ClientEvent = MetaEvent | TokenEvent | DoneEvent | ErrorEvent

const DONE_STATUSES: readonly string[] = ['COMPLETED', 'PARTIAL', 'NO_CONTEXT', 'FAILED']

/**
 * Narrows a parsed JSON payload to a client event.
 * Checks only the required fields; the backend contract tests own full schema validation.
 */
export function toClientEvent(value: unknown): ClientEvent | null {
  if (!isRecord(value)) return null
  switch (value.event) {
    case 'meta':
      return typeof value.requestId === 'string' ? (value as unknown as MetaEvent) : null
    case 'token':
      return typeof value.t === 'string' ? (value as unknown as TokenEvent) : null
    case 'done':
      return typeof value.status === 'string' && DONE_STATUSES.includes(value.status)
        ? (value as unknown as DoneEvent)
        : null
    case 'error':
      return typeof value.code === 'string' && typeof value.message === 'string'
        ? (value as unknown as ErrorEvent)
        : null
    default:
      return null
  }
}
