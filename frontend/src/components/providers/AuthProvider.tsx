import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, login as apiLogin, logout as apiLogout, onSessionLost, refreshAccessToken } from '@/api/auth'
import { AuthContext, type AuthState } from '@/hooks/useAuth'
import type { Credentials, Me } from '@/types/auth'

const LOST_MESSAGE: Record<string, string> = {
  AUTH_REFRESH_REUSED: '보안을 위해 로그아웃되었습니다. 다시 로그인해주세요.',
  AUTH_REFRESH_EXPIRED: '로그인 유효 기간(7일)이 지났습니다. 다시 로그인해주세요.',
}

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [status, setStatus] = useState<AuthState['status']>('checking')
  const [user, setUser] = useState<Me | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // restore the session from the refresh cookie (the token itself is not persisted)
  useEffect(() => {
    let cancelled = false
    refreshAccessToken()
      .then((ok) => (ok ? fetchMe() : null))
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setStatus(me === null ? 'guest' : 'user')
      })
      .catch(() => {
        if (cancelled) return
        setUser(null)
        setStatus('guest')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(
    () =>
      onSessionLost((code) => {
        setUser(null)
        setStatus('guest')
        setNotice(LOST_MESSAGE[code] ?? '로그인이 만료되었습니다. 다시 로그인해주세요.')
      }),
    [],
  )

  const login = useCallback(async (credentials: Credentials) => {
    await apiLogin(credentials)
    const me = await fetchMe()
    setUser(me)
    setStatus('user')
    setNotice(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
      setStatus('guest')
    }
  }, [])

  const clearNotice = useCallback(() => setNotice(null), [])

  const value = useMemo<AuthState>(
    () => ({ status, user, notice, login, logout, clearNotice }),
    [status, user, notice, login, logout, clearNotice],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
