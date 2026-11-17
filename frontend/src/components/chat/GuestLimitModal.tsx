// Guest limit modal (docs/ui/screenshots/11, policy §9.2 GUEST_QUOTA_EXCEEDED → 로그인 유도 모달).

import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import '@/styles/auth.css'

interface GuestLimitModalProps {
  code: string
  onClose: () => void
}

export function GuestLimitModal({ code, onClose }: GuestLimitModalProps): JSX.Element {
  const primaryRef = useRef<HTMLAnchorElement>(null)
  useEffect(() => {
    primaryRef.current?.focus()
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const sessionLimit = code === 'GUEST_SESSION_LIMIT'
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guest-limit-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="emoji">🔒</div>
        <h2 id="guest-limit-title">{sessionLimit ? '게스트 이용이 잠시 제한되었습니다' : '게스트 질문 한도 도달'}</h2>
        <p>
          {sessionLimit
            ? '같은 네트워크에서 게스트 세션이 너무 많이 만들어졌습니다.'
            : '5회 무료 질문을 모두 사용했습니다.'}
          <br />
          로그인하면 질문 제한 없이 이용할 수 있습니다.
        </p>
        <Link ref={primaryRef} to="/signup" className="btn btn-primary btn-block">
          회원가입으로 계속하기
        </Link>
        <Link to="/login" className="btn btn-outline btn-block">
          로그인
        </Link>
        <p className="faint">가입 시 대화 이력 저장 · 비교 모드 · 무제한 질문 제공</p>
      </div>
    </div>
  )
}
