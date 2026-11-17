import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { GUEST_QUESTION_LIMIT, GuestUsageContext, type GuestUsageState } from '@/hooks/useGuestUsage'
import { useSources } from '@/hooks/useSources'

export function GuestUsageProvider({ children }: { children: ReactNode }): JSX.Element {
  const { guest } = useSources()
  const [used, setUsed] = useState(0)

  // Start from the server count (api-spec 2.1 `guest`) so a reload keeps the real usage.
  useEffect(() => {
    if (guest !== null) setUsed(Math.min(guest.used, GUEST_QUESTION_LIMIT))
  }, [guest])

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
