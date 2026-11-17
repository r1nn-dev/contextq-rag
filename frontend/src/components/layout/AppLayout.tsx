import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppLayout(): JSX.Element {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
