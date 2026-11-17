// New conversation start screen for signed-in users (docs/ui/screenshots/06).

import { versionTone } from '@/hooks/useSources'
import type { ChatMode } from '@/types/chat'
import type { Source } from '@/types/sources'

interface StartPanelProps {
  sources: Source[]
  sourceKey: string | null
  onSource: (sourceKey: string) => void
  mode: ChatMode
  /** undefined while compare mode is unavailable */
  onMode?: (mode: ChatMode) => void
  compareHint: string
}

export function StartPanel({ sources, sourceKey, onSource, mode, onMode, compareHint }: StartPanelProps): JSX.Element {
  return (
    <div className="center-fill start-panel">
      <div className="emoji">⚡</div>
      <h2>버전을 선택하고 시작하세요</h2>
      <p className="muted">질문할 버전과 답변 모드를 선택하세요.</p>

      <div className="start-group">
        <div className="start-label">버전 선택</div>
        <div className="start-options">
          {sources.map((s) => (
            <button
              key={s.sourceKey}
              type="button"
              className={`chip chip-lg ${versionTone(sources, s.sourceKey)}`}
              aria-pressed={mode === 'SINGLE' && s.sourceKey === sourceKey}
              disabled={mode === 'COMPARE'}
              onClick={() => onSource(s.sourceKey)}
            >
              <span className="chip-dot" />
              {s.versionLabel}
            </button>
          ))}
        </div>
        <div className="start-note">
          {sources.map((s) => `${s.versionLabel} · ${s.activeRun.commitSha.slice(0, 7)} · ${s.activeRun.ingestedAt} 수집`).join('  |  ')}
        </div>
      </div>

      <div className="start-group">
        <div className="start-label">답변 모드</div>
        <div className="start-options">
          <button
            type="button"
            className="chip chip-lg"
            aria-pressed={mode === 'SINGLE'}
            onClick={() => onMode?.('SINGLE')}
          >
            단일 모드
          </button>
          <button
            type="button"
            className="chip chip-lg"
            aria-pressed={mode === 'COMPARE'}
            disabled={onMode === undefined}
            onClick={() => onMode?.('COMPARE')}
          >
            비교 모드
          </button>
        </div>
        <div className="start-note">{compareHint}</div>
      </div>
    </div>
  )
}
