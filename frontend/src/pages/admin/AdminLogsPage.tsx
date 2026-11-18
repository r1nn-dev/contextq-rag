// Request log (sidebar "시스템 로그", api-spec 5.5): ended answers and guest usage, newest first.
// No question text or email is shown (policy §9.4); the request ID leads to the server log.

import { useCallback, useEffect, useState } from 'react'
import { fetchLogs } from '@/api/admin'
import { ApiError } from '@/api/http'
import { ForbiddenView } from '@/components/admin/AdminLayout'
import type { AdminLog, LogLevel } from '@/types/admin'
import { describeLog } from '@/utils/adminLog'
import { formatDateTime } from '@/utils/format'

const LEVEL_CLASS: Record<LogLevel, string> = {
  INFO: 'tag tag-muted',
  WARN: 'tag tag-warn',
  ERROR: 'tag tag-danger',
}

const LEVELS: Array<{ value: LogLevel | null; label: string }> = [
  { value: null, label: '전체' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'WARN', label: 'WARN' },
  { value: 'INFO', label: 'INFO' },
]

export function AdminLogsPage(): JSX.Element {
  const [level, setLevel] = useState<LogLevel | null>(null)
  const [rows, setRows] = useState<AdminLog[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(async (filter: LogLevel | null, before: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const page = await fetchLogs(filter, before)
      setRows((prev) => (before === null ? page.items : [...prev, ...page.items]))
      setCursor(page.cursor)
      setHasNext(page.hasNext)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError('UNKNOWN', '로그를 불러오지 못했습니다.', 0))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(level, null)
  }, [load, level])

  if (error?.code === 'FORBIDDEN') return <ForbiddenView />

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>시스템 로그</h1>
        <span className="spacer" />
        <label className="faint">
          수준{' '}
          <select
            aria-label="로그 수준"
            value={level ?? ''}
            onChange={(e) => setLevel(e.target.value === '' ? null : (e.target.value as LogLevel))}
          >
            {LEVELS.map((l) => (
              <option key={l.label} value={l.value ?? ''}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void load(level, null)} disabled={loading}>
          새로 고침
        </button>
      </header>
      <div className="admin-body">
        {error !== null && (
          <div className="form-alert" role="alert">
            {error.message}
          </div>
        )}
        <p className="faint">답변이 끝난 요청(회원)과 게스트 이용 기록입니다. 질문 내용은 표시하지 않습니다.</p>
        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col">시각</th>
              <th scope="col">수준</th>
              <th scope="col">사용자</th>
              <th scope="col">요청 ID</th>
              <th scope="col">내용</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.at}-${r.requestId ?? 'guest'}-${i}`}>
                <td>{formatDateTime(r.at)}</td>
                <td>
                  <span className={LEVEL_CLASS[r.level]}>{r.level}</span>
                </td>
                <td>{r.actor === 'GUEST' ? '게스트' : `#${r.userId ?? '—'}`}</td>
                <td className="mono faint">{r.requestId ?? '—'}</td>
                <td>{describeLog(r)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="faint empty-row">
                  표시할 로그가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {hasNext && (
          <button type="button" className="btn btn-outline btn-sm" onClick={() => void load(level, cursor)} disabled={loading}>
            더 보기
          </button>
        )}
      </div>
    </div>
  )
}
