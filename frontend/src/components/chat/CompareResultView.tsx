// Compare result (docs/ui/screenshots/13): A/B summaries side by side, then the change list.

import type { VersionTone } from '@/hooks/useSources'
import type { CompareResult, CompareSide } from '@/types/sse'
import { Markdown, type CitationContext } from './Markdown'

export interface CompareSideInfo {
  label: string
  tone: VersionTone
  sourceCount: number
}

function citeList(citations: readonly (string | number)[]): string {
  return citations.map((c) => `[${String(c)}]`).join('')
}

function Side({ side, info, cite }: { side: CompareSide; info: CompareSideInfo; cite: CitationContext }): JSX.Element {
  return (
    <section className="compare-side">
      <header className="compare-side-head">
        <span className={`tag ${info.tone}`}>{info.label}</span>
        <span className="spacer" />
        <span className={`tag ${info.tone}`}>참고 {info.sourceCount}개</span>
      </header>
      <div className="compare-side-body">
        {side.no_evidence ? (
          <p className="compare-empty">해당 버전 문서에서 근거를 찾지 못했습니다.</p>
        ) : (
          <Markdown text={side.summary} cite={cite} />
        )}
      </div>
    </section>
  )
}

interface CompareResultViewProps {
  result: CompareResult
  a: CompareSideInfo
  b: CompareSideInfo
  cite: CitationContext
}

export function CompareResultView({ result, a, b, cite }: CompareResultViewProps): JSX.Element {
  return (
    <div className="compare">
      <div className="compare-grid">
        <Side side={result.version_a} info={a} cite={cite} />
        <Side side={result.version_b} info={b} cite={cite} />
      </div>

      {result.changes.length > 0 ? (
        <table className="compare-changes">
          <caption>변경점</caption>
          <thead>
            <tr>
              <th scope="col">항목</th>
              <th scope="col">
                <span className={`tag ${a.tone}`}>{a.label}</span>
              </th>
              <th scope="col">
                <span className={`tag ${b.tone}`}>{b.label}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {result.changes.map((change) => (
              <tr key={change.aspect}>
                <th scope="row">{change.aspect}</th>
                <td>
                  <Markdown text={`${change.a} ${citeList(change.citations_a)}`} cite={cite} />
                </td>
                <td>
                  <Markdown text={`${change.b} ${citeList(change.citations_b)}`} cite={cite} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        (result.version_a.no_evidence || result.version_b.no_evidence) && (
          <p className="faint compare-note">한쪽 버전에 근거가 없어 변경점 목록은 만들지 않았습니다.</p>
        )
      )}
    </div>
  )
}
