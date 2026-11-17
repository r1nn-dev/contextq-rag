// User management (docs/ui/screenshots/17).
// api-spec has no user list API yet: preview rows appear only in mock mode; real mode
// shows a notice until the contract is added to docs/specs/api-spec.md.

import { useEffect, useMemo, useState } from 'react'
import type { UserPreviewRow } from '@/types/admin'

const PREVIEW = import.meta.env.VITE_USE_MOCK === 'true'

const ROLE_CLASS: Record<UserPreviewRow['role'], string> = {
  admin: 'tag tag-danger',
  user: 'tag tone-c',
  guest: 'tag tag-muted',
}

export function AdminUsersPage(): JSX.Element {
  const [rows, setRows] = useState<UserPreviewRow[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    if (!PREVIEW) return
    let cancelled = false
    void import('@/mocks/adminPreview').then((m) => {
      if (!cancelled) setRows(m.USER_PREVIEW)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q === '' ? rows : rows.filter((r) => r.email.toLowerCase().includes(q))
  }, [rows, query])

  const count = (role: UserPreviewRow['role']): number => rows.filter((r) => r.role === role).length

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>사용자 관리</h1>
        <span className="spacer" />
        <input
          className="search-input"
          type="search"
          placeholder="이메일 검색…"
          aria-label="이메일 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>

      <div className="admin-body">
        <div className="form-alert info">
          사용자 목록 API가 API 명세에 아직 없습니다. {PREVIEW ? '아래는 개발용 예시 데이터입니다.' : 'API가 추가되면 연결합니다.'}
        </div>

        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col">이메일</th>
              <th scope="col">가입일</th>
              <th scope="col">역할</th>
              <th scope="col">총 질문</th>
              <th scope="col">이용 한도</th>
              <th scope="col">액션</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.email}>
                <td>{r.email}</td>
                <td>{r.joinedAt}</td>
                <td>
                  <span className={ROLE_CLASS[r.role]}>{r.role}</span>
                </td>
                <td>{r.totalQuestions ?? '—'}</td>
                <td>{r.quota}</td>
                <td>
                  <button type="button" className="btn btn-ghost btn-sm" disabled title="API 미정">
                    편집
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="faint empty-row">
                  표시할 사용자가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {rows.length > 0 && (
          <p className="faint table-foot">
            총 {rows.length}명 · 관리자 {count('admin')} · 일반 사용자 {count('user')} · 게스트 {count('guest')}
          </p>
        )}
      </div>
    </div>
  )
}
