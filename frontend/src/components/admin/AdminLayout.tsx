// Admin shell (docs/ui/screenshots/16, 17). Guests go to login; non-admins see 403.

import { Link, Navigate, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Icon, type IconName } from '@/components/common/Icon'
import { Logo } from '@/components/common/Logo'
import { useAuth } from '@/hooks/useAuth'
import '@/styles/admin.css'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/admin/index', label: '인덱스 현황', icon: 'grid' },
  { to: '/admin/users', label: '사용자 관리', icon: 'users' },
  { to: '/admin/logs', label: '시스템 로그', icon: 'activity' },
]

export function ForbiddenView(): JSX.Element {
  return (
    <div className="full-center">
      <div className="center-fill">
        <div className="emoji">🚫</div>
        <h1>접근 권한이 없습니다</h1>
        <p className="muted">관리자 계정으로 로그인해야 볼 수 있는 화면입니다.</p>
        <Link to="/chat" className="btn btn-outline">
          채팅으로 돌아가기
        </Link>
      </div>
    </div>
  )
}

export function AdminLayout(): JSX.Element {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'checking') {
    return (
      <div className="full-center">
        <span className="spinner" />
      </div>
    )
  }
  if (user === null) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  // api-spec 0.6: /admin/** is ROLE_ADMIN only (FORBIDDEN for ROLE_USER)
  if (user.role !== 'ROLE_ADMIN') return <ForbiddenView />

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/admin/index" className="sidebar-logo">
          <Logo subtitle="관리자 패널" />
        </Link>
        <div className="sidebar-body">
          <div className="sidebar-section-label">시스템</div>
          <nav className="admin-nav" aria-label="관리자 메뉴">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} className="admin-nav-item">
                <Icon name={item.icon} size={15} /> {item.label}
              </NavLink>
            ))}
          </nav>
          <Link to="/chat" className="conv-more">
            서비스 화면으로 <Icon name="arrowRight" size={12} />
          </Link>
        </div>
        <div className="sidebar-footer">
          <span className="avatar avatar-admin">{user.email.charAt(0).toUpperCase()}</span>
          <span className="email">{user.email}</span>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
