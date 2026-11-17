import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { GUEST_QUESTION_LIMIT, GuestUsageContext, type GuestUsageState } from '@/hooks/useGuestUsage'

export function GuestUsageProvider({ children }: { children: ReactNode }): JSX.Element {
  const [used, setUsed] = useState(0)

  const recordQuestion = useCallback(
    () => setUsed((n) => Math.min(n + 1, GUEST_QUESTION_LIMIT)),
    [],
  )
  const markExhausted = useCallback(() => setUsed(GUEST_QUESTION_LIMIT), [])

  const value = useMemo<GuestUsageState>(
    () => ({ used, limit: GUEST_QUESTION_LIMIT, recordQuestion, markExhausted }),
    [used, recordQuestion, markExhausted],
  )
  return <GuestUsageContext.Provider value={value}>{children}</GuestUsageContext.Provider>
}
