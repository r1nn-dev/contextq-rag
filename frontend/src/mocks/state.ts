// Mutable in-memory state of the mock backend. Reset on page reload.

import type { Role } from '@/types/auth'

export const GUEST_LIMIT = 5

/** Short token lifetime so the silent refresh path is exercised during manual testing. */
export const ACCESS_TTL_MS = 60_000

export interface MockUser {
  userId: number
  email: string
  /** null for seeded demo accounts, which accept any well-formed password */
  password: string | null
  role: Role
  createdAt: string
  failures: number
  lockedUntil: number
}

export const mockState = {
  guestUsed: 0,
  nextUserId: 3,
  users: new Map<string, MockUser>([
    [
      'admin@contextq.dev',
      { userId: 1, email: 'admin@contextq.dev', password: null, role: 'ROLE_ADMIN', createdAt: '2026-10-01T00:00:00Z', failures: 0, lockedUntil: 0 },
    ],
    [
      'user@example.com',
      { userId: 2, email: 'user@example.com', password: null, role: 'ROLE_USER', createdAt: '2026-10-15T00:00:00Z', failures: 0, lockedUntil: 0 },
    ],
  ]),
  accessTokens: new Map<string, { userId: number; expiresAt: number }>(),
  /** stands in for the HttpOnly refresh cookie */
  refreshUserId: null as number | null,
}

export function userById(userId: number): MockUser | null {
  for (const user of mockState.users.values()) if (user.userId === userId) return user
  return null
}
