import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

/** Sends guests to the login screen and returns them here afterwards. */
export function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'guest') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
