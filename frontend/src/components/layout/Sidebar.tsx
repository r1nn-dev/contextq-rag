import { Link, useNavigate } from 'react-router-dom'
import { Icon } from '@/components/common/Icon'
import { Logo } from '@/components/common/Logo'
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

export function Sidebar(): JSX.Element {
  const navigate = useNavigate()

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

        <div className="sidebar-section-label">게스트 세션</div>
        <GuestQuotaCard />
        <p className="sidebar-note">로그인하면 무제한으로 이용할 수 있습니다.</p>
        <div className="sidebar-note">
          <Link to="/login" className="btn btn-primary btn-sm btn-block">
            로그인 / 회원가입
          </Link>
        </div>
      </div>
    </aside>
  )
}
