// docs/specs/api-spec.md > 1. 인증, policy §1.2

import type { Credentials, Me, SignupResponse, TokenResponse } from '@/types/auth'
import { ApiError, requestJson, setRefresher } from './http'
import { getAccessToken, setAccessToken } from './tokenStore'

type SessionLostListener = (code: string) => void
const sessionLostListeners = new Set<SessionLostListener>()

/** Called when a signed-in session ends without the user logging out (expiry, reuse detection). */
export function onSessionLost(listener: SessionLostListener): () => void {
  sessionLostListeners.add(listener)
  return () => {
    sessionLostListeners.delete(listener)
  }
}

export function signup(credentials: Credentials): Promise<SignupResponse> {
  return requestJson<SignupResponse>(
    '/auth/signup',
    { method: 'POST', body: JSON.stringify(credentials) },
    { auth: false },
  )
}

export async function login(credentials: Credentials): Promise<void> {
  const token = await requestJson<TokenResponse>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify(credentials) },
    { auth: false },
  )
  setAccessToken(token.accessToken)
}

async function runRefresh(conflictRetried: boolean): Promise<boolean> {
  try {
    const token = await requestJson<TokenResponse>('/auth/refresh', { method: 'POST' }, { auth: false })
    setAccessToken(token.accessToken)
    return true
  } catch (err) {
    const code = err instanceof ApiError ? err.code : 'NETWORK_ERROR'
    // another tab rotated first; the cookie already holds the new token (api-spec 1.3)
    if (code === 'AUTH_REFRESH_CONFLICT' && !conflictRetried) return runRefresh(true)
    const hadSession = getAccessToken() !== null
    setAccessToken(null)
    if (hadSession || code === 'AUTH_REFRESH_REUSED') {
      sessionLostListeners.forEach((listener) => listener(code))
    }
    return false
  }
}

let inflight: Promise<boolean> | null = null

/** Single-flight refresh: concurrent callers in this tab share one request (policy §1.2). */
export function refreshAccessToken(): Promise<boolean> {
  if (inflight === null) {
    inflight = runRefresh(false).finally(() => {
      inflight = null
    })
  }
  return inflight
}

setRefresher(refreshAccessToken)

export async function logout(): Promise<void> {
  try {
    await requestJson<null>('/auth/logout', { method: 'POST' }, { auth: false })
  } finally {
    setAccessToken(null)
  }
}

export function fetchMe(): Promise<Me> {
  return requestJson<Me>('/auth/me')
}
