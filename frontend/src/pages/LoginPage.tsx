import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '@/api/http'
import { LogoMark } from '@/components/common/Logo'
import { useAuth } from '@/hooks/useAuth'
import { isRecord } from '@/types/api'
import '@/styles/auth.css'

function returnPath(state: unknown): string {
  return isRecord(state) && typeof state.from === 'string' ? state.from : '/chat'
}

function lockMessage(err: ApiError): string {
  if (err.retryAfterSec === null) return err.message
  const minutes = Math.max(1, Math.ceil(err.retryAfterSec / 60))
  return `로그인 시도가 너무 많습니다. ${minutes}분 후 다시 시도해주세요.`
}

export function LoginPage(): JSX.Element {
  const { login, notice, clearNotice } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    if (email.trim() === '' || password === '') {
      setError('이메일과 비밀번호를 입력해주세요.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await login({ email: email.trim().toLowerCase(), password })
      navigate(returnPath(location.state), { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'AUTH_LOCKED') setError(lockMessage(err))
      // same message whether or not the account exists (policy §1.2)
      else if (err instanceof ApiError && err.code === 'AUTH_INVALID_CREDENTIALS')
        setError('이메일 또는 비밀번호가 올바르지 않습니다.')
      else setError(err instanceof ApiError ? err.message : '로그인하지 못했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={(e) => void submit(e)} noValidate>
        <Link to="/" className="auth-brand">
          <LogoMark /> ContextQ
        </Link>
        <h1>다시 돌아오셨군요</h1>
        <p className="subtitle">계속하려면 로그인하세요</p>

        {notice !== null && (
          <div className="form-alert info" role="status">
            {notice}
          </div>
        )}
        {error !== null && (
          <div className="form-alert" role="alert">
            {error}
          </div>
        )}

        <div className="field">
          <label htmlFor="login-email">이메일</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            placeholder="user@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              clearNotice()
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">비밀번호</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            placeholder="비밀번호를 입력하세요"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={pending}>
          {pending ? '로그인 중…' : '로그인'}
        </button>

        <div className="auth-links">
          <span>
            계정이 없으신가요? <Link to="/signup">회원가입</Link>
          </span>
          <Link to="/chat" className="plain">
            게스트로 계속하기
          </Link>
        </div>
      </form>
    </div>
  )
}
