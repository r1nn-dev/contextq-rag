import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signup } from '@/api/auth'
import { ApiError } from '@/api/http'
import { LogoMark } from '@/components/common/Logo'
import { useAuth } from '@/hooks/useAuth'
import { validateCredentials } from '@/types/auth'
import '@/styles/auth.css'

export function SignupPage(): JSX.Element {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    const found = validateCredentials(email, password, confirm)
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length > 0) return

    const credentials = { email: email.trim().toLowerCase(), password }
    setPending(true)
    try {
      await signup(credentials)
      // signup returns only userId; log in with the same credentials
      await login(credentials)
      navigate('/chat', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.details.length > 0) {
        setErrors(Object.fromEntries(err.details.map((d) => [d.field, d.reason])))
      } else {
        setFormError(err instanceof ApiError ? err.message : '회원가입하지 못했습니다.')
      }
    } finally {
      setPending(false)
    }
  }

  const fieldError = (name: string): JSX.Element | null =>
    errors[name] !== undefined ? (
      <span className="field-error" id={`signup-${name}-error`}>
        {errors[name]}
      </span>
    ) : null

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={(e) => void submit(e)} noValidate>
        <Link to="/" className="auth-brand">
          <LogoMark /> ContextQ
        </Link>
        <h1>계정 만들기</h1>
        <p className="subtitle">버전별 공식 문서 Q&amp;A 플랫폼</p>

        {formError !== null && (
          <div className="form-alert" role="alert">
            {formError}
          </div>
        )}

        <div className="field">
          <label htmlFor="signup-email">이메일</label>
          <input
            id="signup-email"
            type="email"
            autoComplete="email"
            placeholder="user@example.com"
            value={email}
            aria-invalid={errors.email !== undefined}
            aria-describedby="signup-email-error"
            onChange={(e) => setEmail(e.target.value)}
          />
          {fieldError('email')}
        </div>
        <div className="field">
          <label htmlFor="signup-password">비밀번호</label>
          <input
            id="signup-password"
            type="password"
            autoComplete="new-password"
            placeholder="8자 이상, 영문·숫자 포함"
            value={password}
            aria-invalid={errors.password !== undefined}
            aria-describedby="signup-password-error"
            onChange={(e) => setPassword(e.target.value)}
          />
          {fieldError('password')}
        </div>
        <div className="field">
          <label htmlFor="signup-confirm">비밀번호 확인</label>
          <input
            id="signup-confirm"
            type="password"
            autoComplete="new-password"
            placeholder="비밀번호를 다시 입력하세요"
            value={confirm}
            aria-invalid={errors.confirm !== undefined}
            aria-describedby="signup-confirm-error"
            onChange={(e) => setConfirm(e.target.value)}
          />
          {fieldError('confirm')}
        </div>

        <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={pending}>
          {pending ? '가입 중…' : '회원가입'}
        </button>

        <div className="divider">또는</div>
        <div className="auth-links">
          <span>
            이미 계정이 있으신가요? <Link to="/login">로그인</Link>
          </span>
          <Link to="/chat" className="plain">
            게스트로 계속하기 (5회 무료)
          </Link>
        </div>
      </form>
    </div>
  )
}
