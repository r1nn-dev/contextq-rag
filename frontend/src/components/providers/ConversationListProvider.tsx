import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchConversations } from '@/api/conversations'
import { useAuth } from '@/hooks/useAuth'
import { ConversationListContext, type ConversationListState } from '@/hooks/useConversationList'
import type { ConversationSummary } from '@/types/conversation'

export function ConversationListProvider({ children }: { children: ReactNode }): JSX.Element {
  const { user } = useAuth()
  const [status, setStatus] = useState<ConversationListState['status']>('idle')
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [version, setVersion] = useState(0)
  const userId = user?.userId ?? null

  useEffect(() => {
    if (userId === null) {
      setItems([])
      setStatus('idle')
      return
    }
    let cancelled = false
    setStatus((s) => (s === 'ready' ? s : 'loading'))
    fetchConversations()
      .then((page) => {
        if (cancelled) return
        setItems(page.items)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [userId, version])

  const refresh = useCallback(() => setVersion((v) => v + 1), [])
  const value = useMemo<ConversationListState>(() => ({ status, items, refresh }), [status, items, refresh])
  return <ConversationListContext.Provider value={value}>{children}</ConversationListContext.Provider>
}
