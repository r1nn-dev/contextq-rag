import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Icon } from '@/components/common/Icon'
import { Logo } from '@/components/common/Logo'
import { useAuth } from '@/hooks/useAuth'
import { useGuestUsage } from '@/hooks/useGuestUsage'

export function GuestQuotaCard(): JSX.Element {
  const { used, limit } = useGuestUsage()
  return (
    <div className="guest-card">
      <div className="guest-card-title">게스트 모드</div>
      <div className="quota-dots" aria-hidden="true">
        {Array.from({ length: limit }, (_, i) => (
          <span key={i} className={i < used ? 'quota-dot used' : 'quota-dot'} />
        ))}
      </div>
      <div className="guest-card-count">
        {limit}회 중 {used}회 사용
      </div>
    </div>
  )
}

export function UserFooter(): JSX.Element | null {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  if (user === null) return null
  const admin = user.role === 'ROLE_ADMIN'
  return (
    <div className="sidebar-footer">
      <span className={admin ? 'avatar avatar-admin' : 'avatar'}>{user.email.charAt(0).toUpperCase()}</span>
      <span className="email" title={user.email}>
        {user.email}
      </span>
      {admin && (
        <Link to="/admin/index" className="btn-ghost icon-btn" title="관리자 패널" aria-label="관리자 패널">
          <Icon name="grid" size={16} />
        </Link>
      )}
      <button
        type="button"
        className="btn-ghost icon-btn"
        title="로그아웃"
        aria-label="로그아웃"
        onClick={() => {
          void logout().then(() => navigate('/chat', { state: { fresh: Date.now() } }))
        }}
      >
        <Icon name="logout" size={16} />
      </button>
    </div>
  )
}

/** Signed-in sidebar body; F-3 fills the recent conversation list. */
export function Sidebar({ children }: { children?: ReactNode }): JSX.Element {
  const navigate = useNavigate()
  const { status } = useAuth()

  return (
    <aside className="sidebar">
      <Link to="/" className="sidebar-logo">
        <Logo subtitle="RAG Q&A Platform" />
      </Link>
      <div className="sidebar-body">
        <button
          type="button"
          className="btn btn-primary sidebar-new-btn"
          onClick={() => navigate('/chat', { state: { fresh: Date.now() } })}
        >
          <Icon name="plus" size={14} /> 새 대화
        </button>

        {status === 'guest' && (
          <>
            <div className="sidebar-section-label">게스트 세션</div>
            <GuestQuotaCard />
            <p className="sidebar-note">로그인하면 무제한으로 이용할 수 있습니다.</p>
            <div className="sidebar-note">
              <Link to="/login" className="btn btn-primary btn-sm btn-block">
                로그인 / 회원가입
              </Link>
            </div>
          </>
        )}
        {status === 'user' && children}
      </div>
      <UserFooter />
    </aside>
  )
}
