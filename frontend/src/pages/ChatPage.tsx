// Chat screen: new conversation, live stream, and reopened conversations
// (docs/ui/screenshots/03, 06~10, 15).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { fetchConversation } from '@/api/conversations'
import { ApiError } from '@/api/http'
import { AssistantMessage, type SnapshotInfo } from '@/components/chat/AssistantMessage'
import { Composer } from '@/components/chat/Composer'
import { GuestLimitModal } from '@/components/chat/GuestLimitModal'
import { SourcePanel, type PanelSource } from '@/components/chat/SourcePanel'
import { StartPanel } from '@/components/chat/StartPanel'
import { Icon } from '@/components/common/Icon'
import { turnsFromDetail } from '@/hooks/savedTurns'
import { useAuth } from '@/hooks/useAuth'
import { useConversationList } from '@/hooks/useConversationList'
import { useGuestUsage } from '@/hooks/useGuestUsage'
import { findSource, frameworkName, useSources, versionTone } from '@/hooks/useSources'
import { useSseQuery, type Turn } from '@/hooks/useSseQuery'
import { isRecord } from '@/types/api'
import type { ConversationDetail } from '@/types/conversation'
import type { Source } from '@/types/sources'
import { formatDate } from '@/utils/format'
import '@/styles/chat.css'

const READ_ONLY_CODES = new Set(['CONVERSATION_FULL', 'SOURCE_UNAVAILABLE'])

function freshToken(state: unknown): number {
  return isRecord(state) && typeof state.fresh === 'number' ? state.fresh : 0
}

function snapshotOf(turn: Turn, sources: Source[]): SnapshotInfo | null {
  const meta = turn.meta
  if (meta === null || meta.commitSha === undefined || meta.ingestedAt === undefined) return null
  return {
    label: findSource(sources, meta.sourceKey)?.versionLabel ?? meta.sourceKey ?? '',
    commitSha: meta.commitSha,
    ingestedAt: meta.ingestedAt,
  }
}

export function ChatPage(): JSX.Element {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const routeId = params.conversationId !== undefined ? Number(params.conversationId) : null

  const { status, sources, errorMessage, reload } = useSources()
  const guest = useGuestUsage()
  const { user } = useAuth()
  const conversationList = useConversationList()
  const isGuest = user === null

  const [limitCode, setLimitCode] = useState<string | null>(null)
  const [pickedKey, setPickedKey] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [activeRank, setActiveRank] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<ConversationDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [readOnly, setReadOnly] = useState(false)
  const [continuing, setContinuing] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  const { turns, conversationId, busy, ask, stop, reset } = useSseQuery({
    onMeta: () => {
      if (isGuest) guest.recordQuestion()
    },
    onPreStreamError: (err) => {
      if (err.code === 'GUEST_QUOTA_EXCEEDED') guest.markExhausted()
      if (err.code === 'GUEST_QUOTA_EXCEEDED' || err.code === 'GUEST_SESSION_LIMIT') setLimitCode(err.code)
      if (READ_ONLY_CODES.has(err.code)) setReadOnly(true)
    },
    onFinish: () => {
      if (!isGuest) conversationList.refresh()
    },
  })

  const conversationRef = useRef(conversationId)
  conversationRef.current = conversationId
  const routeRef = useRef(routeId)
  routeRef.current = routeId
  const stateRef = useRef<unknown>(location.state)
  stateRef.current = location.state
  // react-router v6 hands out a new navigate on every location change; effects below must
  // not re-run for that, or the URL sync would bounce back to the streamed conversation
  const navigateRef = useRef(navigate)
  navigateRef.current = navigate

  // "새 대화" navigates with a fresh token; start over when it changes
  const fresh = freshToken(location.state)
  useEffect(() => {
    reset()
    setDraft('')
    setFocusKey(null)
    setActiveRank(null)
    setLoaded(null)
    setReadOnly(false)
    setContinuing(false)
  }, [fresh, reset])

  // open a saved conversation unless it is the one being streamed in this view
  useEffect(() => {
    if (routeId === null || isGuest) return
    if (Number.isNaN(routeId)) {
      navigateRef.current('/history', { replace: true })
      return
    }
    if (routeId === conversationRef.current) return
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    fetchConversation(routeId)
      .then((detail) => {
        if (cancelled) return
        reset({ conversationId: detail.conversationId, turns: turnsFromDetail(detail) })
        setLoaded(detail)
        setReadOnly(detail.status === 'READ_ONLY')
        setContinuing(false)
        setFocusKey(null)
        setActiveRank(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // missing and someone else's conversation look the same (INV-14) → back to the list
        if (err instanceof ApiError && err.code === 'CONVERSATION_NOT_FOUND') {
          navigateRef.current('/history', { replace: true, state: { notice: '대화를 찾을 수 없습니다.' } })
          return
        }
        setLoadError(err instanceof ApiError ? err.message : '대화를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      setLoading(false)
    }
  }, [routeId, isGuest, reset])

  // the first meta of a new conversation carries its id; move the URL there without remounting
  useEffect(() => {
    if (conversationId !== null && conversationId !== routeRef.current) {
      navigateRef.current(`/chat/${conversationId}`, { replace: true, state: stateRef.current })
    }
  }, [conversationId])

  useEffect(() => {
    const el = listRef.current
    if (el !== null) el.scrollTop = el.scrollHeight
  }, [turns])

  // version is fixed once the conversation starts (INV-10)
  const sourceKey = loaded?.sourceKey ?? turns[0]?.request.sourceKey ?? pickedKey ?? sources[0]?.sourceKey ?? null
  const source = findSource(sources, sourceKey)
  const tone = versionTone(sources, sourceKey)
  const framework = frameworkName(sources) ?? '공식 문서'
  // the tab-local count is approximate; the input stays enabled so the server's
  // GUEST_QUOTA_EXCEEDED response decides and opens the login modal
  const exhausted = isGuest && guest.used >= guest.limit

  const panelTurn = useMemo(() => {
    const focused = turns.find((t) => t.key === focusKey)
    if (focused?.meta?.sources !== undefined && focused.meta.sources.length > 0) return focused
    // otherwise follow the latest turn; a NO_CONTEXT answer has no panel (screenshot 10)
    const latest = turns[turns.length - 1]
    return latest !== undefined && (latest.meta?.sources?.length ?? 0) > 0 ? latest : null
  }, [turns, focusKey])

  const panelSources = useMemo<PanelSource[]>(
    () =>
      (panelTurn?.meta?.sources ?? []).map((s) => ({
        ...s,
        versionLabel: findSource(sources, panelTurn?.meta?.sourceKey)?.versionLabel ?? '',
        tone: versionTone(sources, panelTurn?.meta?.sourceKey),
      })),
    [panelTurn, sources],
  )

  const submit = useCallback(
    (question: string) => {
      if (sourceKey === null) return
      setDraft('')
      setFocusKey(null)
      setActiveRank(null)
      void ask(question, { mode: 'SINGLE', sourceKey, sourceKeyA: null, sourceKeyB: null })
    },
    [ask, sourceKey],
  )

  const startNew = (): void => navigate('/chat', { state: { fresh: Date.now() } })

  // saved conversations belong to signed-in users only (api-spec 0.6)
  if (isGuest && routeId !== null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (status === 'loading' || loading) {
    return (
      <div className="center-fill">
        <span className="spinner" />
        <p className="muted">{loading ? '대화를 불러오는 중입니다…' : '버전 목록을 불러오는 중입니다…'}</p>
      </div>
    )
  }
  if (loadError !== null) {
    return (
      <div className="center-fill">
        <div className="emoji">⚠️</div>
        <h2>대화를 불러오지 못했습니다</h2>
        <p className="muted">{loadError}</p>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => navigate('/history')}>
          이력으로 돌아가기
        </button>
      </div>
    )
  }
  if (status === 'error' || sources.length === 0) {
    return (
      <div className="center-fill">
        <div className="emoji">⚠️</div>
        <h2>질문할 수 있는 버전이 없습니다</h2>
        <p className="muted">{errorMessage ?? '활성화된 문서 인덱스가 없습니다. 잠시 후 다시 시도해주세요.'}</p>
        <button type="button" className="btn btn-outline btn-sm" onClick={reload}>
          다시 불러오기
        </button>
      </div>
    )
  }

  const last = turns[turns.length - 1]
  const lastNoContext = last?.done?.status === 'NO_CONTEXT'
  const placeholder = exhausted
    ? `게스트 질문 ${guest.limit}회를 모두 사용했습니다. 로그인하면 계속 질문할 수 있습니다.`
    : turns.length === 0
      ? `${framework}에 대해 무엇이든 질문하세요… (Ctrl+Enter로 전송)`
      : lastNoContext
        ? '다시 질문해보세요…'
        : '추가 질문을 입력하세요… (Ctrl+Enter)'
  const showPanel = panelSources.length > 0
  const versionLabel = source?.versionLabel ?? findSource(sources, loaded?.sourceKey)?.versionLabel ?? ''

  const status_ = busy ? (
    <span className="header-status">
      <span className="spinner" /> 답변 생성 중…
    </span>
  ) : loaded !== null ? (
    <span className="faint header-status">
      {readOnly ? '읽기 전용 · ' : ''}
      {formatDate(loaded.updatedAt)}
    </span>
  ) : (
    showPanel && (
      <span className="faint header-status">
        <Icon name="clip" size={13} /> 참고 {panelSources.length}개
      </span>
    )
  )

  let header: JSX.Element
  if (loaded !== null) {
    header = (
      <header className="page-header">
        <h1 className="conv-heading">{loaded.title}</h1>
        <span className={`tag ${tone}`}>{versionLabel}</span>
        <span className="spacer" />
        {status_}
      </header>
    )
  } else if (turns.length > 0) {
    header = (
      <header className="page-header">
        <span className={`tag ${tone}`}>{versionLabel}</span>
        <span className="tag tag-plain">단일 모드</span>
        <span className="spacer" />
        {status_}
      </header>
    )
  } else if (!isGuest) {
    header = (
      <header className="page-header">
        <h1>새 대화</h1>
      </header>
    )
  } else {
    header = (
      <div className="chat-toolbar">
        <span className="faint">버전</span>
        {sources.map((s) => (
          <button
            key={s.sourceKey}
            type="button"
            className={`chip ${versionTone(sources, s.sourceKey)}`}
            aria-pressed={s.sourceKey === sourceKey}
            title={`${s.displayName} · ${s.activeRun.commitSha.slice(0, 7)} · ${s.activeRun.ingestedAt} 수집`}
            onClick={() => setPickedKey(s.sourceKey)}
          >
            {s.versionLabel}
          </button>
        ))}
        <span className="faint toolbar-gap">모드</span>
        <button type="button" className="chip" aria-pressed="true">
          단일 모드
        </button>
        <button type="button" className="chip" disabled title="로그인 후 이용 가능">
          비교 모드 <Icon name="lock" size={12} />
        </button>
      </div>
    )
  }

  let footer: JSX.Element
  if (readOnly) {
    footer = (
      <div className="chat-actions">
        <span className="muted">읽기 전용 대화입니다. 메시지 한도에 도달했거나 더 이상 질문할 수 없는 버전입니다.</span>
        <button type="button" className="btn btn-primary" onClick={startNew}>
          새 대화
        </button>
      </div>
    )
  } else if (loaded !== null && !continuing && !busy) {
    footer = (
      <div className="chat-actions">
        <button type="button" className="btn btn-primary" onClick={() => setContinuing(true)}>
          이어서 질문하기
        </button>
        <button type="button" className="btn btn-outline" onClick={startNew}>
          새 대화
        </button>
      </div>
    )
  } else {
    footer = (
      <Composer
        placeholder={placeholder}
        hint={source !== null ? `${source.versionLabel} — ${source.displayName} 공식 문서 검색 · Ctrl+Enter로 전송` : null}
        disabled={busy}
        value={draft}
        onChange={setDraft}
        onSubmit={submit}
        onStop={stop}
        streaming={busy}
        autoFocus={continuing}
      />
    )
  }

  return (
    <div className="chat-layout">
      <section className="chat-main">
        {isGuest && (
          <div className="banner banner-warn">
            <Icon name="info" size={15} />
            게스트 모드 · 질문 {guest.limit}회 중 {guest.used}회 사용 · 비교 모드 비활성
          </div>
        )}
        {header}

        <div className="chat-scroll" ref={listRef}>
          {turns.length === 0 && !isGuest ? (
            <StartPanel
              sources={sources}
              sourceKey={sourceKey}
              onSource={setPickedKey}
              mode="SINGLE"
              compareHint="비교 모드: 두 버전 답변을 나란히 확인"
            />
          ) : turns.length === 0 ? (
            <div className="center-fill">
              <div className="emoji">💬</div>
              <h2>{framework}에 대해 질문해보세요</h2>
              <p className="muted">
                {source?.versionLabel} 문서를 기반으로 답변합니다
                {source !== null && (
                  <span className="faint">
                    {' '}
                    · {source.activeRun.commitSha.slice(0, 7)} · {source.activeRun.ingestedAt} 수집
                  </span>
                )}
              </p>
            </div>
          ) : (
            <div className="turns">
              {turns.map((turn) => (
                <div key={turn.key} className="turn">
                  <div className="user-bubble">{turn.question}</div>
                  <AssistantMessage
                    turn={turn}
                    snapshot={snapshotOf(turn, sources)}
                    versionLabel={findSource(sources, turn.request.sourceKey)?.versionLabel ?? ''}
                    canRetry={!readOnly}
                    onRetry={() => submit(turn.question)}
                    onCitation={(rank) => {
                      setFocusKey(turn.key)
                      setActiveRank(rank)
                    }}
                    onSuggest={(q) => {
                      setContinuing(true)
                      setDraft(q)
                    }}
                    onFocus={() => setFocusKey(turn.key)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {footer}
      </section>

      {limitCode !== null && <GuestLimitModal code={limitCode} onClose={() => setLimitCode(null)} />}

      {showPanel && (
        <SourcePanel
          sources={panelSources}
          streaming={panelTurn?.phase === 'streaming'}
          activeRank={panelTurn?.key === focusKey ? activeRank : null}
        />
      )}
    </div>
  )
}
