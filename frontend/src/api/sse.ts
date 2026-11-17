// Minimal SSE frame parser for fetch + ReadableStream (ADR-003).
// Handles only what the backend sends: `data:` lines, blank-line frame breaks,
// and `: ping` comments (api-spec 3.1 하트비트), which are ignored.

export interface SseParser {
  push(chunk: string): void
  flush(): void
}

export function createSseParser(onData: (data: string) => void): SseParser {
  let buffer = ''
  let pendingCr = false

  const emitFrame = (frame: string): void => {
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('data:')) {
        const value = line.slice(5)
        dataLines.push(value.startsWith(' ') ? value.slice(1) : value)
      }
      // `:` comments and `event:`/`id:` fields are ignored; the event type is in the JSON body
    }
    if (dataLines.length > 0) onData(dataLines.join('\n'))
  }

  return {
    push(chunk: string): void {
      let text = (pendingCr ? '\r' : '') + chunk
      // keep a trailing CR until the next chunk shows whether it is part of CRLF
      pendingCr = text.endsWith('\r')
      if (pendingCr) text = text.slice(0, -1)
      buffer += text.replace(/\r\n?/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        emitFrame(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
      }
    },
    flush(): void {
      if (buffer.trim() !== '') emitFrame(buffer)
      buffer = ''
      pendingCr = false
    },
  }
}
