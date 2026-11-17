// Single-mode chat (docs/ui/screenshots/03, 07~10).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AssistantMessage, type SnapshotInfo } from '@/components/chat/AssistantMessage'
import { Composer } from '@/components/chat/Composer'
import { GuestLimitModal } from '@/components/chat/GuestLimitModal'
import { SourcePanel, type PanelSource } from '@/components/chat/SourcePanel'
import { StartPanel } from '@/components/chat/StartPanel'
import { Icon } from '@/components/common/Icon'
import { useAuth } from '@/hooks/useAuth'
import { useGuestUsage } from '@/hooks/useGuestUsage'
import { findSource, frameworkName, useSources, versionTone } from '@/hooks/useSources'
import { useSseQuery, type Turn } from '@/hooks/useSseQuery'
import { isRecord } from '@/types/api'
import type { Source } from '@/types/sources'
import '@/styles/chat.css'

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
  const { status, sources, errorMessage, reload } = useSources()
  const guest = useGuestUsage()
  const { user } = useAuth()
  const isGuest = user === null
  const [limitCode, setLimitCode] = useState<string | null>(null)
  const [pickedKey, setPickedKey] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [activeRank, setActiveRank] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const { turns, busy, ask, stop, reset } = useSseQuery({
    onMeta: () => {
      if (isGuest) guest.recordQuestion()
    },
    onPreStreamError: (err) => {
      if (err.code === 'GUEST_QUOTA_EXCEEDED') guest.markExhausted()
      if (err.code === 'GUEST_QUOTA_EXCEEDED' || err.code === 'GUEST_SESSION_LIMIT') setLimitCode(err.code)
    },
  })

  // "새 대화" navigates with a fresh token; start over when it changes
  const fresh = freshToken(location.state)
  useEffect(() => {
    reset()
    setDraft('')
    setFocusKey(null)
    setActiveRank(null)
  }, [fresh, reset])

  useEffect(() => {
    const el = listRef.current
    if (el !== null) el.scrollTop = el.scrollHeight
  }, [turns])

  // version is fixed once the conversation starts (INV-10)
  const sourceKey = turns[0]?.request.sourceKey ?? pickedKey ?? sources[0]?.sourceKey ?? null
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

  if (status === 'loading') {
    return (
      <div className="center-fill">
        <span className="spinner" />
        <p className="muted">버전 목록을 불러오는 중입니다…</p>
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

  return (
    <div className="chat-layout">
      <section className="chat-main">
        {isGuest && (
          <div className="banner banner-warn">
            <Icon name="info" size={15} />
            게스트 모드 · 질문 {guest.limit}회 중 {guest.used}회 사용 · 비교 모드 비활성
          </div>
        )}

        {turns.length === 0 && !isGuest ? (
          <header className="page-header">
            <h1>새 대화</h1>
          </header>
        ) : turns.length === 0 ? (
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
        ) : (
          <header className="page-header">
            <span className={`tag ${tone}`}>{source?.versionLabel}</span>
            <span className="tag tag-plain">단일 모드</span>
            <span className="spacer" />
            {busy ? (
              <span className="header-status">
                <span className="spinner" /> 답변 생성 중…
              </span>
            ) : (
              showPanel && (
                <span className="faint header-status">
                  <Icon name="clip" size={13} /> 참고 {panelSources.length}개
                </span>
              )
            )}
          </header>
        )}

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
                    onRetry={() => submit(turn.question)}
                    onCitation={(rank) => {
                      setFocusKey(turn.key)
                      setActiveRank(rank)
                    }}
                    onSuggest={setDraft}
                    onFocus={() => setFocusKey(turn.key)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        <Composer
          placeholder={placeholder}
          hint={source !== null ? `${source.versionLabel} — ${source.displayName} 공식 문서 검색 · Ctrl+Enter로 전송` : null}
          disabled={busy}
          value={draft}
          onChange={setDraft}
          onSubmit={submit}
          onStop={stop}
          streaming={busy}
        />
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
