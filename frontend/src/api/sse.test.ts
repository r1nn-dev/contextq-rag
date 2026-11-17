import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse'

function collect(chunks: string[]): string[] {
  const out: string[] = []
  const parser = createSseParser((data) => out.push(data))
  chunks.forEach((c) => parser.push(c))
  parser.flush()
  return out
}

describe('createSseParser', () => {
  it('emits one payload per blank-line separated frame', () => {
    expect(collect(['data: {"a":1}\n\ndata: {"b":2}\n\n'])).toEqual(['{"a":1}', '{"b":2}'])
  })

  it('joins a frame split across chunks', () => {
    expect(collect(['da', 'ta: {"t":"한', '글"}\n', '\n'])).toEqual(['{"t":"한글"}'])
  })

  it('treats CRLF as a line break even when CR and LF land in different chunks', () => {
    expect(collect(['data: x\r', '\n\r\n', 'data: y\r\n\r\n'])).toEqual(['x', 'y'])
  })

  it('joins multi-line data with a newline', () => {
    expect(collect(['data: line1\ndata: line2\n\n'])).toEqual(['line1\nline2'])
  })

  it('ignores heartbeat comments and event fields', () => {
    expect(collect([': ping\n\n', 'event: meta\ndata: m\n\n'])).toEqual(['m'])
  })

  it('emits a trailing frame without a final blank line on flush', () => {
    expect(collect(['data: last'])).toEqual(['last'])
  })
})
