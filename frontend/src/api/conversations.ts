// GET /api/v1/conversations, GET /api/v1/conversations/{id} (docs/specs/api-spec.md > 4)

import type { CursorPage } from '@/types/api'
import type { ConversationDetail, ConversationSummary } from '@/types/conversation'
import { requestJson } from './http'

export const CONVERSATION_PAGE_SIZE = 20

export function fetchConversations(before: string | null = null): Promise<CursorPage<ConversationSummary>> {
  const params = new URLSearchParams({ size: String(CONVERSATION_PAGE_SIZE) })
  if (before !== null) params.set('before', before)
  return requestJson<CursorPage<ConversationSummary>>(`/conversations?${params.toString()}`)
}

export function fetchConversation(conversationId: number): Promise<ConversationDetail> {
  return requestJson<ConversationDetail>(`/conversations/${conversationId}`)
}
