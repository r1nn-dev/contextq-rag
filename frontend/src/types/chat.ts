// POST /api/v1/chat/stream request (docs/specs/api-spec.md > 3.1)

export type ChatMode = 'SINGLE' | 'COMPARE'

export interface ChatStreamRequest {
  conversationId: number | null
  question: string
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
}

/** trim 후 1~1,000자 (policy §5.1). */
export const QUESTION_MAX_LENGTH = 1000
