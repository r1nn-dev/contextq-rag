// Conversation history (docs/ui/screenshots/14). Cursor paging by 20 (api-spec 4.1).

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { fetchConversations } from '@/api/conversations'
import { ApiError } from '@/api/http'
import { ConversationTag } from '@/components/layout/RecentConversations'
import { isRecord } from '@/types/api'
import type { ConversationSummary } from '@/types/conversation'
import { formatDateTime } from '@/utils/format'
import '@/styles/history.css'

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  PARTIAL: { label: '중단됨', className: 'tag tag-warn' },
  FAILED: { label: '실패', className: 'tag tag-danger' },
  NO_CONTEXT: { label: '근거 없음', className: 'tag tag-muted' },
}

export function HistoryPage(): JSX.Element {
  const location = useLocation()
  const notice = isRecord(location.state) && typeof location.state.notice === 'string' ? location.state.notice : null
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const load = useCallback(async (before: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const page = await fetchConversations(before)
      setItems((prev) => (before === null ? page.items : [...prev, ...page.items]))
      setCursor(page.cursor)
      setHasNext(page.hasNext)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '대화 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(null)
  }, [load])

  // the list API has no search parameter, so search covers the pages loaded so far
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q === '' ? items : items.filter((item) => item.title.toLowerCase().includes(q))
  }, [items, query])

  return (
    <div className="history">
      <header className="page-header">
        <h1>대화 이력</h1>
        <span className="spacer" />
        <input
          className="search-input"
          type="search"
          placeholder="이력 검색…"
          aria-label="이력 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>

      <div className="history-body">
        {notice !== null && <div className="form-alert info">{notice}</div>}
        {error !== null && (
          <div className="form-alert" role="alert">
            {error}{' '}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load(null)}>
              다시 시도
            </button>
          </div>
        )}

        {filtered.map((item) => {
          const badge = item.lastMessageStatus !== null ? STATUS_BADGE[item.lastMessageStatus] : undefined
          return (
            <Link key={item.conversationId} to={`/chat/${item.conversationId}`} className="history-card">
              <div className="history-title">{item.title}</div>
              <div className="history-meta">
                <ConversationTag item={item} />
                <span className="tag tag-muted">{item.mode === 'COMPARE' ? '비교 모드' : '단일'}</span>
                {item.status === 'READ_ONLY' && <span className="tag tag-muted">읽기 전용</span>}
                {badge !== undefined && <span className={badge.className}>{badge.label}</span>}
                <span className="faint">메시지 {item.messageCount}개</span>
                <span className="spacer" />
                <span className="faint">{formatDateTime(item.updatedAt)}</span>
              </div>
            </Link>
          )
        })}

        {loading && (
          <div className="center-fill">
            <span className="spinner" />
          </div>
        )}
        {!loading && items.length === 0 && error === null && (
          <div className="center-fill">
            <div className="emoji">🗂️</div>
            <h2>아직 대화가 없습니다</h2>
            <Link to="/chat" className="btn btn-primary btn-sm">
              새 대화 시작하기
            </Link>
          </div>
        )}

        {!loading && items.length > 0 && (
          <div className="history-foot">
            {query.trim() !== '' ? `검색 결과 ${filtered.length}개 · ` : ''}
            {hasNext ? `지금까지 ${items.length}개의 대화` : `총 ${items.length}개의 대화`}
            {hasNext && (
              <button type="button" className="btn btn-outline btn-sm" onClick={() => void load(cursor)}>
                더 보기
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
