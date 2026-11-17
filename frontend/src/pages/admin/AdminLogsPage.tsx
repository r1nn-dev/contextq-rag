// System log menu (docs/ui/screenshots/16·17 sidebar). No screen mockup or API exists yet;
// preview rows appear only in mock mode.

import { useEffect, useState } from 'react'
import type { LogPreviewRow } from '@/types/admin'
import { formatDateTime } from '@/utils/format'

const PREVIEW = import.meta.env.VITE_USE_MOCK === 'true'

const LEVEL_CLASS: Record<LogPreviewRow['level'], string> = {
  INFO: 'tag tag-muted',
  WARN: 'tag tag-warn',
  ERROR: 'tag tag-danger',
}

export function AdminLogsPage(): JSX.Element {
  const [rows, setRows] = useState<LogPreviewRow[]>([])

  useEffect(() => {
    if (!PREVIEW) return
    let cancelled = false
    void import('@/mocks/adminPreview').then((m) => {
      if (!cancelled) setRows(m.LOG_PREVIEW)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>시스템 로그</h1>
      </header>
      <div className="admin-body">
        <div className="form-alert info">
          시스템 로그 API와 화면 목업이 아직 없습니다. {PREVIEW ? '아래는 개발용 예시 데이터입니다.' : 'API가 추가되면 연결합니다.'}
        </div>
        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col">시각</th>
              <th scope="col">수준</th>
              <th scope="col">요청 ID</th>
              <th scope="col">내용</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.at}-${r.requestId}`}>
                <td>{formatDateTime(r.at)}</td>
                <td>
                  <span className={LEVEL_CLASS[r.level]}>{r.level}</span>
                </td>
                <td className="mono faint">{r.requestId}</td>
                <td>{r.message}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="faint empty-row">
                  표시할 로그가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
