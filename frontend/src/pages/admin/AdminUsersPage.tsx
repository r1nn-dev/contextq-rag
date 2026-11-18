// User management (docs/ui/screenshots/17, api-spec 5.3 · 5.4).
// Accounts only: guests are not accounts (their usage is on the index and log screens).
// The only edit is lifting a login lock (policy §1.2 · §10.3).

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { fetchUsers, unlockUser } from '@/api/admin'
import { ApiError } from '@/api/http'
import { ForbiddenView } from '@/components/admin/AdminLayout'
import type { AdminUser, AdminUsersResponse } from '@/types/admin'
import { formatDate, formatDateTime, formatNumber } from '@/utils/format'

const ROLE_LABEL: Record<AdminUser['role'], { label: string; className: string }> = {
  ROLE_ADMIN: { label: 'admin', className: 'tag tag-danger' },
  ROLE_USER: { label: 'user', className: 'tag tone-c' },
}

function asApiError(err: unknown, fallback: string): ApiError {
  return err instanceof ApiError ? err : new ApiError('UNKNOWN', fallback, 0)
}

export function AdminUsersPage(): JSX.Element {
  const [query, setQuery] = useState('')
  const [applied, setApplied] = useState('')
  const [rows, setRows] = useState<AdminUser[]>([])
  const [page, setPage] = useState<AdminUsersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)

  const load = useCallback(async (search: string, before: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchUsers(search, before)
      setPage(res)
      setRows((prev) => (before === null ? res.items : [...prev, ...res.items]))
    } catch (err) {
      setError(asApiError(err, '사용자 목록을 불러오지 못했습니다.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(applied, null)
  }, [load, applied])

  const search = (e: FormEvent): void => {
    e.preventDefault()
    setNotice(null)
    setApplied(query.trim())
  }

  const unlock = async (user: AdminUser): Promise<void> => {
    setPendingId(user.userId)
    setNotice(null)
    try {
      const updated = await unlockUser(user.userId)
      setRows((prev) => prev.map((r) => (r.userId === updated.userId ? updated : r)))
      setNotice(`${updated.email} 계정의 잠금을 해제했습니다.`)
      setPage((prev) =>
        prev === null ? prev : { ...prev, summary: { ...prev.summary, locked: Math.max(0, prev.summary.locked - 1) } },
      )
    } catch (err) {
      setNotice(asApiError(err, '잠금을 해제하지 못했습니다.').message)
    } finally {
      setPendingId(null)
    }
  }

  if (error?.code === 'FORBIDDEN') return <ForbiddenView />

  const summary = page?.summary

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>사용자 관리</h1>
        <span className="spacer" />
        <form onSubmit={search} role="search">
          <input
            className="search-input"
            type="search"
            placeholder="이메일 검색…"
            aria-label="이메일 검색"
            maxLength={254}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
      </header>

      <div className="admin-body">
        {error !== null && (
          <div className="form-alert" role="alert">
            {error.message}
          </div>
        )}
        {notice !== null && (
          <div className="form-alert info" role="status">
            {notice}
          </div>
        )}

        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col">이메일</th>
              <th scope="col">가입일</th>
              <th scope="col">역할</th>
              <th scope="col">상태</th>
              <th scope="col">총 질문</th>
              <th scope="col">오늘 사용</th>
              <th scope="col">액션</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.userId}>
                <td>{r.email}</td>
                <td>{formatDate(r.createdAt)}</td>
                <td>
                  <span className={ROLE_LABEL[r.role].className}>{ROLE_LABEL[r.role].label}</span>
                </td>
                <td>
                  {r.status === 'LOCKED' ? (
                    <span className="tag tag-warn" title={r.lockedUntil !== null ? `${formatDateTime(r.lockedUntil)}까지` : undefined}>
                      잠김
                    </span>
                  ) : (
                    <span className="tag tag-muted">정상</span>
                  )}
                </td>
                <td>{formatNumber(r.totalQuestions)}</td>
                <td>
                  {formatNumber(r.todayQuotaUsed)} / {formatNumber(r.dailyQuota)}
                </td>
                <td>
                  {r.status === 'LOCKED' ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void unlock(r)}
                      disabled={pendingId === r.userId}
                    >
                      잠금 해제
                    </button>
                  ) : (
                    <span className="faint">—</span>
                  )}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="faint empty-row">
                  표시할 사용자가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {page?.hasNext === true && (
          <button type="button" className="btn btn-outline btn-sm" onClick={() => void load(applied, page.cursor)} disabled={loading}>
            더 보기
          </button>
        )}

        {summary !== undefined && (
          <p className="faint table-foot">
            총 {formatNumber(summary.totalUsers)}명 · 관리자 {formatNumber(summary.admins)} · 일반 사용자{' '}
            {formatNumber(summary.members)} · 잠김 {formatNumber(summary.locked)}
          </p>
        )}
      </div>
    </div>
  )
}
