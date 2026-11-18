// POST /api/v1/chat/stream request (docs/specs/api-spec.md > 3.1)

export type ChatMode = 'SINGLE' | 'COMPARE'

/** One message of the guest rewrite context (api-spec 3.1 history 규칙). */
export interface HistoryItem {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatStreamRequest {
  conversationId: number | null
  question: string
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
  /** guests only; logged-in users rely on the server DB */
  history?: HistoryItem[]
}

/** trim 후 1~1,000자 (policy §5.1). */
export const QUESTION_MAX_LENGTH = 1000
