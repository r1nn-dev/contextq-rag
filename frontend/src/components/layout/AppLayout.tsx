import { Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Sidebar } from './Sidebar'

export function AppLayout(): JSX.Element {
  const { status } = useAuth()
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        {status === 'checking' ? (
          <div className="center-fill">
            <span className="spinner" />
          </div>
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  )
}
