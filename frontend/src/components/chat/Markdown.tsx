// Lightweight renderer for answer text. Builds React elements only (no HTML injection),
// supporting what answers use: code fences, inline code, bold, lists, headings and
// citations [n] / [A1] (policy §7 인용 규칙).

import { Fragment, type ReactNode } from 'react'

type Block =
  | { kind: 'code'; lang: string; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'h'; text: string }
  | { kind: 'ul' | 'ol'; items: string[] }

const FENCE = /^```\s*([\w+-]*)\s*$/
const BULLET = /^\s*[-*]\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/
const HEADING = /^#{1,6}\s+(.*)$/
const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[(?:[AB]?\d+)\])/g

function parseBlocks(source: string): Block[] {
  const lines = source.split('\n')
  const blocks: Block[] = []
  let para: string[] = []
  const flush = (): void => {
    if (para.length > 0) blocks.push({ kind: 'p', text: para.join('\n') })
    para = []
  }

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const fence = FENCE.exec(line)
    if (fence !== null) {
      flush()
      const body: string[] = []
      i += 1
      // an unclosed fence (still streaming) runs to the end of the text
      while (i < lines.length && !FENCE.test(lines[i])) {
        body.push(lines[i])
        i += 1
      }
      blocks.push({ kind: 'code', lang: fence[1], text: body.join('\n') })
      continue
    }
    const listMatch = BULLET.exec(line) ?? NUMBERED.exec(line)
    if (listMatch !== null) {
      flush()
      const kind = BULLET.test(line) ? 'ul' : 'ol'
      const pattern = kind === 'ul' ? BULLET : NUMBERED
      const items: string[] = []
      while (i < lines.length) {
        const m = pattern.exec(lines[i])
        if (m === null) break
        items.push(m[1])
        i += 1
      }
      i -= 1
      blocks.push({ kind, items })
      continue
    }
    const heading = HEADING.exec(line)
    if (heading !== null) {
      flush()
      blocks.push({ kind: 'h', text: heading[1] })
      continue
    }
    if (line.trim() === '') {
      flush()
      continue
    }
    para.push(line)
  }
  flush()
  return blocks
}

export interface CitationContext {
  /** ranks present in meta.sources, as strings */
  valid: ReadonlySet<string>
  /** done.invalidCitations, as strings */
  invalid: ReadonlySet<string>
  onSelect: (rank: string) => void
}

function renderInline(text: string, cite: CitationContext): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part === '') return null
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={i}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (/^\[[AB]?\d+\]$/.test(part)) {
      const rank = part.slice(1, -1)
      const usable = cite.valid.has(rank) && !cite.invalid.has(rank)
      // out-of-range or invalidated numbers render inactive (INV-08)
      return usable ? (
        <button key={i} type="button" className="cite" onClick={() => cite.onSelect(rank)}>
          [{rank}]
        </button>
      ) : (
        <span key={i} className="cite cite-invalid" title="확인되지 않은 인용 번호">
          [{rank}]
        </span>
      )
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}

export function Markdown({ text, cite }: { text: string; cite: CitationContext }): JSX.Element {
  return (
    <div className="md">
      {parseBlocks(text).map((block, i) => {
        switch (block.kind) {
          case 'code':
            return (
              <pre key={i} className="md-code" data-lang={block.lang || undefined}>
                <code>{block.text}</code>
              </pre>
            )
          case 'h':
            return (
              <p key={i} className="md-h">
                {renderInline(block.text, cite)}
              </p>
            )
          case 'ul':
          case 'ol': {
            const List = block.kind
            return (
              <List key={i}>
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item, cite)}</li>
                ))}
              </List>
            )
          }
          default:
            return <p key={i}>{renderInline(block.text, cite)}</p>
        }
      })}
    </div>
  )
}
