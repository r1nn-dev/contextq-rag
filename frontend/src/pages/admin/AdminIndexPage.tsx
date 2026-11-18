// Index status dashboard (docs/ui/screenshots/16, api-spec 5.1 · 5.2).

import { useCallback, useEffect, useState } from 'react'
import { fetchIndexStatus, triggerIngest } from '@/api/admin'
import { ApiError } from '@/api/http'
import { ForbiddenView } from '@/components/admin/AdminLayout'
import { useSources, versionTone } from '@/hooks/useSources'
import type { AdminSourceStatus, IndexStatusResponse, IngestRunStatus } from '@/types/admin'
import { formatDateTime, formatNumber } from '@/utils/format'

const RUN_BADGE: Partial<Record<IngestRunStatus, { label: string; className: string }>> = {
  ACTIVE: { label: '정상', className: 'tag tag-ok' },
  READY: { label: '활성화 대기', className: 'tag tag-warn' },
  FAILED: { label: '실패', className: 'tag tag-danger' },
  SUPERSEDED: { label: '교체됨', className: 'tag tag-muted' },
  PURGED: { label: '삭제됨', className: 'tag tag-muted' },
}

function runBadge(status: IngestRunStatus): JSX.Element {
  const badge = RUN_BADGE[status] ?? { label: status, className: 'tag tag-plain' }
  return <span className={badge.className}>{badge.label}</span>
}

function versionOf(source: AdminSourceStatus, catalog: ReturnType<typeof useSources>['sources']): string {
  return catalog.find((s) => s.sourceKey === source.sourceKey)?.versionLabel ?? source.displayName
}

function SourceCard({ source }: { source: AdminSourceStatus }): JSX.Element {
  const { sources } = useSources()
  const run = source.activeRun
  const tone = versionTone(sources, source.sourceKey)
  const delta = run !== null && run.prevChunkCount !== null ? run.chunkCount - run.prevChunkCount : null

  return (
    <article className="admin-card">
      <div className="admin-card-head">
        <span className={`tag ${tone}`}>{versionOf(source, sources)}</span>
        {run !== null ? runBadge(run.status) : <span className="tag tag-danger">ACTIVE 없음</span>}
        {!source.enabled && <span className="tag tag-muted">비활성</span>}
        <span className="spacer" />
        <span className="faint">{source.displayName}</span>
      </div>
      {run === null ? (
        <p className="muted">서비스 중인 인덱스가 없습니다(INDEX_NOT_ACTIVE).</p>
      ) : (
        <>
          <dl className="stat-grid">
            <div>
              <dt>청크 수</dt>
              <dd className="stat-big">
                {formatNumber(run.chunkCount)}
                {delta !== null && (
                  <span className={delta >= 0 ? 'delta up' : 'delta down'}>
                    {delta >= 0 ? '+' : ''}
                    {formatNumber(delta)}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>청크 전략</dt>
              <dd className="stat-big">{run.chunkStrategy}</dd>
            </div>
            <div>
              <dt>인덱스 SHA</dt>
              <dd className={`mono sha ${tone}`}>{run.commitSha.slice(0, 12)}</dd>
            </div>
            <div>
              <dt>수집 완료</dt>
              <dd>{formatDateTime(run.completedAt)}</dd>
            </div>
            <div>
              <dt>임베딩</dt>
              <dd>
                {run.embeddingModel} · {formatNumber(run.embeddingTokens)} 토큰 · ${run.embeddingCostUsd.toFixed(3)}
              </dd>
            </div>
            <div>
              <dt>소요 시간</dt>
              <dd>{(run.ingestDurationMs / 1000).toFixed(1)}초</dd>
            </div>
          </dl>
        </>
      )}
      <div className="run-list">
        <div className="run-list-title">최근 수집 이력</div>
        {source.recentRuns.map((r) => (
          <div key={r.ingestRunId} className="run-row">
            <span className="mono faint">#{r.ingestRunId}</span>
            {runBadge(r.status)}
            {r.failureStage !== undefined && <span className="faint">실패 단계: {r.failureStage}</span>}
            <span className="spacer" />
            <span className="faint">{r.startedAt !== null ? formatDateTime(r.startedAt) : '—'}</span>
          </div>
        ))}
      </div>
    </article>
  )
}

function UsageSummary({ usage }: { usage: IndexStatusResponse['usageSummary'] }): JSX.Element {
  const max = Math.max(1, ...usage.last7Days.map((d) => d.totalMessages))
  return (
    <section className="admin-card">
      <div className="admin-card-head">
        <h2>사용량</h2>
        <span className="spacer" />
        <span className="faint">오늘 {usage.today.date}</span>
      </div>
      <dl className="stat-grid four">
        <div>
          <dt>메시지</dt>
          <dd className="stat-big">{formatNumber(usage.today.totalMessages)}</dd>
        </div>
        <div>
          <dt>프롬프트 토큰</dt>
          <dd className="stat-big">{formatNumber(usage.today.promptTokens)}</dd>
        </div>
        <div>
          <dt>완료 토큰</dt>
          <dd className="stat-big">{formatNumber(usage.today.completionTokens)}</dd>
        </div>
        <div>
          <dt>게스트 세션</dt>
          <dd className="stat-big">{formatNumber(usage.today.guestSessions ?? 0)}</dd>
        </div>
      </dl>
      <table className="usage-table">
        <caption className="run-list-title">최근 7일</caption>
        <thead>
          <tr>
            <th scope="col">날짜</th>
            <th scope="col">메시지</th>
            <th scope="col" className="bar-col">
              <span className="sr-only">메시지 막대</span>
            </th>
            <th scope="col">프롬프트 토큰</th>
            <th scope="col">완료 토큰</th>
          </tr>
        </thead>
        <tbody>
          {usage.last7Days.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{formatNumber(d.totalMessages)}</td>
              <td className="bar-col">
                <meter className="usage-bar" min={0} max={max} value={d.totalMessages} />
              </td>
              <td>{formatNumber(d.promptTokens)}</td>
              <td>{formatNumber(d.completionTokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function AdminIndexPage(): JSX.Element {
  const { sources: catalog } = useSources()
  const [data, setData] = useState<IndexStatusResponse | null>(null)
  const [checkedAt, setCheckedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [ingestLocked, setIngestLocked] = useState(false)
  const [ingestMessage, setIngestMessage] = useState<string | null>(null)
  const [pendingKey, setPendingKey] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchIndexStatus())
      setCheckedAt(new Date().toISOString())
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError('UNKNOWN', '인덱스 현황을 불러오지 못했습니다.', 0))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const ingest = async (sourceKey: string): Promise<void> => {
    setPendingKey(sourceKey)
    setIngestMessage(null)
    try {
      const res = await triggerIngest(sourceKey)
      setIngestMessage(`수집을 시작했습니다 (run #${res.ingestRunId}). 진행 상태는 새로 고침으로 확인하세요.`)
    } catch (err) {
      // policy §9.2: FORBIDDEN_IN_PROFILE → 버튼 비활성
      if (err instanceof ApiError && err.code === 'FORBIDDEN_IN_PROFILE') setIngestLocked(true)
      setIngestMessage(err instanceof ApiError ? err.message : '재인덱싱을 시작하지 못했습니다.')
    } finally {
      setPendingKey(null)
    }
  }

  if (error?.code === 'FORBIDDEN') return <ForbiddenView />

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>인덱스 현황</h1>
        <span className="spacer" />
        {checkedAt !== null && <span className="faint header-status">마지막 확인: {formatDateTime(checkedAt)}</span>}
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void load()} disabled={loading}>
          새로 고침
        </button>
      </header>

      <div className="admin-body">
        {error !== null && (
          <div className="form-alert" role="alert">
            {error.message}
          </div>
        )}
        {loading && data === null && (
          <div className="center-fill">
            <span className="spinner" />
          </div>
        )}

        {data !== null && (
          <>
            <div className="admin-grid">
              {data.sources.map((s) => (
                <SourceCard key={s.sourceKey} source={s} />
              ))}
            </div>

            <section className="admin-card">
              <div className="admin-card-head">
                <h2>재인덱싱</h2>
                {ingestLocked && <span className="tag tag-danger">프로덕션 비활성</span>}
              </div>
              <p className="muted">
                로컬·스테이징 환경에서만 수동 재인덱싱이 가능합니다. 운영 환경에서는 거절되며, 새 인덱스는 검증 후
                관리자 명령으로 활성화됩니다.
              </p>
              <div className="ingest-actions">
                {data.sources.map((s) => (
                  <button
                    key={s.sourceKey}
                    type="button"
                    className="btn btn-outline"
                    disabled={ingestLocked || pendingKey !== null}
                    onClick={() => void ingest(s.sourceKey)}
                  >
                    {pendingKey === s.sourceKey ? '요청 중…' : `${versionOf(s, catalog)} 재인덱싱`}
                  </button>
                ))}
              </div>
              {ingestMessage !== null && <p className="faint">{ingestMessage}</p>}
            </section>

            <UsageSummary usage={data.usageSummary} />
          </>
        )}
      </div>
    </div>
  )
}
