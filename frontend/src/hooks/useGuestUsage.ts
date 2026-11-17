// Guest question counter shown in the sidebar and banner.
// Starts from the server count in GET /api/v1/sources `guest` (api-spec 2.1), then this tab
// counts questions whose meta arrived (quota is charged on validation pass, policy §1.3).
// The server's GUEST_QUOTA_EXCEEDED response stays authoritative.

import { createContext, useContext } from 'react'

export const GUEST_QUESTION_LIMIT = 5

export interface GuestUsageState {
  used: number
  limit: number
  recordQuestion: () => void
  markExhausted: () => void
}

export const GuestUsageContext = createContext<GuestUsageState | null>(null)

export function useGuestUsage(): GuestUsageState {
  const value = useContext(GuestUsageContext)
  if (value === null) throw new Error('useGuestUsage must be used inside GuestUsageProvider')
  return value
}
