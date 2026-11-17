// Assistant side of one turn: loading → streaming → done / NO_CONTEXT / error.

import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '@/components/common/Icon'
import type { Turn } from '@/hooks/useSseQuery'
import { CompareResultView, type CompareSideInfo } from './CompareResultView'
import { Markdown, type CitationContext } from './Markdown'

const LOGIN_CODES = new Set(['GUEST_QUOTA_EXCEEDED', 'GUEST_SESSION_LIMIT', 'GUEST_MODE_NOT_ALLOWED'])
const NO_RETRY_CODES = new Set(['CONVERSATION_FULL', 'SOURCE_UNAVAILABLE', 'DAILY_QUOTA_EXCEEDED', 'IN_PROGRESS'])

const NO_CONTEXT_REASON: Record<string, string> = {
  LOW_SIMILARITY: '질문과 가까운 문서의 유사도가 임계값보다 낮아 LLM을 호출하지 않았습니다.',
  LLM_ABSTAIN: '검색된 문서만으로는 답할 수 없다고 판단해 답변을 생성하지 않았습니다.',
}

const NO_CONTEXT_SUGGESTIONS = ['LCEL 체인 구성 방법', 'ChatModel vs LLM 차이', 'Retriever 사용법']

export interface SnapshotInfo {
  label: string
  commitSha: string
  ingestedAt: string
}

interface AssistantMessageProps {
  turn: Turn
  /** one snapshot for single mode, two (A, B) for compare mode */
  snapshots: SnapshotInfo[]
  versionLabel: string
  /** set for compare-mode turns */
  compare?: { a: CompareSideInfo; b: CompareSideInfo }
  /** false for read-only conversations */
  canRetry?: boolean
  onRetry: () => void
  onCitation: (rank: string) => void
  onSuggest: (question: string) => void
  onFocus: () => void
}

export function SnapshotLine({ snapshot }: { snapshot: SnapshotInfo }): JSX.Element {
  // policy §7 스냅샷 표시: "v1.x · e4f5a6b · 2026-10-05 수집"
  return (
    <span className="snapshot">
      {snapshot.label} · {snapshot.commitSha.slice(0, 7)} · {snapshot.ingestedAt} 수집
    </span>
  )
}

export function NoContextCard({
  reason,
  versionLabel,
  onSuggest,
}: {
  reason: string | null | undefined
  versionLabel: string
  onSuggest: (q: string) => void
}): JSX.Element {
  return (
    <div className="no-context">
      <div className="no-context-title">
        <Icon name="info" size={18} /> 관련 문서를 찾지 못했습니다
      </div>
      <p>질문과 관련된 {versionLabel} 공식 문서를 찾지 못했습니다.</p>
      <p>{NO_CONTEXT_REASON[reason ?? ''] ?? '근거 문서가 없어 답변을 생성하지 않았습니다.'}</p>
      {reason !== null && reason !== undefined && <pre className="no-context-code">status: NO_CONTEXT · reason: {reason}</pre>}
      <div className="faint">💡 다른 질문을 시도해보세요:</div>
      <div className="suggestions">
        {NO_CONTEXT_SUGGESTIONS.map((q) => (
          <button key={q} type="button" className="chip" onClick={() => onSuggest(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}

function ErrorBox({ turn, onRetry, canRetry }: { turn: Turn; onRetry: () => void; canRetry: boolean }): JSX.Element | null {
  const error = turn.error
  if (error === null) return null
  let action: ReactNode = (
    <button type="button" className="btn btn-outline btn-sm" onClick={onRetry}>
      <Icon name="refresh" size={13} /> 다시 질문하기
    </button>
  )
  if (LOGIN_CODES.has(error.code)) {
    action = (
      <Link to="/login" className="btn btn-primary btn-sm">
        로그인하고 계속하기
      </Link>
    )
  } else if (NO_RETRY_CODES.has(error.code) || !canRetry) {
    action = null
  }
  return (
    <div className="answer-error" role="alert">
      <div>
        <strong>{error.partial ? '답변이 중간에 중단되었습니다' : '답변을 받지 못했습니다'}</strong>
        <p>{error.message}</p>
        {error.retryAfterSec !== null && <p className="faint">{error.retryAfterSec}초 후 다시 시도할 수 있습니다.</p>}
        <p className="faint mono">{error.code}</p>
      </div>
      {action}
    </div>
  )
}

export function AssistantMessage({
  turn,
  snapshots,
  versionLabel,
  compare,
  canRetry = true,
  onRetry,
  onCitation,
  onSuggest,
  onFocus,
}: AssistantMessageProps): JSX.Element {
  const cite = useMemo<CitationContext>(
    () => ({
      valid: new Set((turn.meta?.sources ?? []).map((s) => String(s.rank))),
      invalid: new Set((turn.done?.invalidCitations ?? []).map(String)),
      onSelect: onCitation,
    }),
    [turn.meta, turn.done, onCitation],
  )

  const noContext = turn.meta?.noContext === true || turn.done?.status === 'NO_CONTEXT'
  if (noContext) {
    return <NoContextCard reason={turn.done?.statusReason} versionLabel={versionLabel} onSuggest={onSuggest} />
  }

  const streaming = turn.phase === 'streaming'
  // compare mode has no token events; the whole result arrives in done (api-spec 부록 B.2)
  const waiting = turn.phase === 'waiting' || (streaming && turn.text === '')
  if (waiting && turn.error === null) {
    return (
      <div className="answer answer-loading">
        <span className="spinner" />
        {turn.meta === null
          ? '참고 문서를 검색하고 있습니다…'
          : compare !== undefined
            ? '두 버전 문서를 비교해 결과를 만들고 있습니다…'
            : '참고 문서를 기반으로 답변을 생성하고 있습니다…'}
      </div>
    )
  }

  const compareResult = compare !== undefined ? (turn.done?.compareResult ?? null) : null
  const hasBody = turn.text !== '' || compareResult !== null
  return (
    <div className={compare !== undefined ? 'answer-group wide' : 'answer-group'}>
      {hasBody && (
        <div className="answer" onClick={onFocus}>
          {compareResult !== null && compare !== undefined ? (
            <CompareResultView result={compareResult} a={compare.a} b={compare.b} cite={cite} />
          ) : (
            <Markdown text={turn.text} cite={cite} />
          )}
          {streaming && <span className="stream-cursor" aria-hidden="true" />}
          {turn.phase === 'done' && (
            <div className="answer-foot">
              {turn.done?.status === 'PARTIAL' && <span className="tag tag-warn">중단됨</span>}
              {snapshots.map((snapshot) => (
                <SnapshotLine key={snapshot.label} snapshot={snapshot} />
              ))}
              {turn.meta?.rewrittenQuery && (
                <details className="rewritten">
                  <summary>검색에 사용된 질의</summary>
                  <span>{turn.meta.rewrittenQuery}</span>
                </details>
              )}
            </div>
          )}
        </div>
      )}
      {turn.done?.status === 'PARTIAL' && canRetry && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
          <Icon name="refresh" size={13} /> 다시 생성
        </button>
      )}
      {turn.done?.status === 'FAILED' && turn.error === null && (
        <ErrorBox
          turn={{ ...turn, error: { code: turn.done.statusReason ?? 'FAILED', message: '답변 생성에 실패했습니다.', partial: hasBody, retryAfterSec: null } }}
          onRetry={onRetry}
          canRetry={canRetry}
        />
      )}
      <ErrorBox turn={turn} onRetry={onRetry} canRetry={canRetry} />
    </div>
  )
}
