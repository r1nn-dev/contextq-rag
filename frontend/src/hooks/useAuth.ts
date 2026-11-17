import { createContext, useContext } from 'react'
import type { Credentials, Me } from '@/types/auth'

export interface AuthState {
  /** 'checking' while the startup refresh decides between guest and user */
  status: 'checking' | 'guest' | 'user'
  user: Me | null
  /** one-off message shown on the login screen (e.g. reuse detection) */
  notice: string | null
  login: (credentials: Credentials) => Promise<void>
  logout: () => Promise<void>
  clearNotice: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

/** Display name is the part before '@' (policy §1.1 표시 이름). */
export function displayName(email: string): string {
  return email.split('@')[0] ?? email
}
