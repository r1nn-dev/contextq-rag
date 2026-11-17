// Right-hand reference panel filled from the meta event (UI-02, policy §7 출처 카드 표시).

import { useEffect, useRef } from 'react'
import { Icon } from '@/components/common/Icon'
import type { VersionTone } from '@/hooks/useSources'
import type { SseSource } from '@/types/sse'

export interface PanelSource extends SseSource {
  versionLabel: string
  tone: VersionTone
}

function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function fileOf(permalink: string): string {
  try {
    const { pathname } = new URL(permalink)
    return pathname.split('/').pop() ?? ''
  } catch {
    return ''
  }
}

function SourceCard({ source, active }: { source: PanelSource; active: boolean }): JSX.Element {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active])

  const segments = source.headingPath.split('>').map((s) => s.trim())
  const title = segments[segments.length - 1] ?? source.headingPath
  const parent = segments.slice(0, -1).join(' > ')

  return (
    <article ref={ref} className={active ? 'source-card active' : 'source-card'}>
      <div className={`source-rank ${source.tone}`}>[{String(source.rank)}]</div>
      <div className="source-title">{title}</div>
      <div className="source-host">
        {hostOf(source.siteUrl)} <span className={`tag ${source.tone}`}>{source.versionLabel}</span>
      </div>
      <div className="source-sub">
        {parent !== '' ? `${parent} · ` : ''}
        {fileOf(source.permalink)} · 유사도 {source.similarity.toFixed(2)}
      </div>
      <div className="source-links">
        <a href={source.permalink} target="_blank" rel="noreferrer noopener">
          원문 보기(고정) <Icon name="external" size={11} />
        </a>
        <a href={source.siteUrl} target="_blank" rel="noreferrer noopener">
          문서 사이트(현재) <Icon name="external" size={11} />
        </a>
      </div>
    </article>
  )
}

interface SourcePanelProps {
  sources: PanelSource[]
  streaming: boolean
  activeRank: string | null
}

export function SourcePanel({ sources, streaming, activeRank }: SourcePanelProps): JSX.Element {
  return (
    <aside className="source-panel" aria-label="참고 문서">
      <header className="source-panel-head">
        <Icon name="file" size={15} />
        <span>참고 문서{streaming ? ' (meta)' : ''}</span>
        <span className="source-count">{sources.length}</span>
      </header>
      <div className="source-panel-body">
        {streaming && (
          <div className="source-status">
            <Icon name="check" size={12} /> 출처 로드 완료 · 답변 생성 중
          </div>
        )}
        {sources.map((s) => (
          <SourceCard key={String(s.rank)} source={s} active={activeRank === String(s.rank)} />
        ))}
      </div>
    </aside>
  )
}
