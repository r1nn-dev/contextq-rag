// First page of the signed-in user's conversations, shared by the sidebar and refreshed
// after each answer so new conversations appear right away.

import { createContext, useContext } from 'react'
import type { ConversationSummary } from '@/types/conversation'

export interface ConversationListState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  items: ConversationSummary[]
  refresh: () => void
}

export const ConversationListContext = createContext<ConversationListState | null>(null)

export function useConversationList(): ConversationListState {
  const value = useContext(ConversationListContext)
  if (value === null) throw new Error('useConversationList must be used inside ConversationListProvider')
  return value
}
