import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchSources } from '@/api/sources'
import { ApiError } from '@/api/http'
import { SourcesContext, type SourcesState } from '@/hooks/useSources'
import type { ComparePair, GuestUsage, Source } from '@/types/sources'

export function SourcesProvider({ children }: { children: ReactNode }): JSX.Element {
  const [status, setStatus] = useState<SourcesState['status']>('loading')
  const [sources, setSources] = useState<Source[]>([])
  const [comparePairs, setComparePairs] = useState<ComparePair[]>([])
  const [guest, setGuest] = useState<GuestUsage | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    fetchSources()
      .then((data) => {
        if (cancelled) return
        setSources(data.sources.filter((s) => s.enabled))
        setComparePairs(data.comparePairs)
        setGuest(data.guest ?? null)
        setErrorMessage(null)
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setErrorMessage(err instanceof ApiError ? err.message : '버전 목록을 불러오지 못했습니다.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])

  const value = useMemo<SourcesState>(
    () => ({ status, sources, comparePairs, guest, errorMessage, reload }),
    [status, sources, comparePairs, guest, errorMessage, reload],
  )
  return <SourcesContext.Provider value={value}>{children}</SourcesContext.Provider>
}
