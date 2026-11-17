// POST /api/v1/chat/stream (docs/specs/api-spec.md > 3.1)

import type { ChatStreamRequest } from '@/types/chat'
import { toClientEvent, type ClientEvent } from '@/types/sse'
import { ApiError, readApiError, send, STREAM_INTERRUPTED } from './http'
import { createSseParser } from './sse'

/**
 * Opens the chat stream and calls onEvent for each contract event.
 * Pre-stream failures throw ApiError (plain JSON response).
 * Resolves when the stream closes; the caller decides whether done/error arrived.
 */
export async function streamChat(
  request: ChatStreamRequest,
  onEvent: (event: ClientEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await send('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(request),
    signal,
  })
  if (!res.ok) throw await readApiError(res)
  if (res.body === null) {
    throw new ApiError(STREAM_INTERRUPTED, '응답 스트림을 열지 못했습니다.', res.status)
  }

  const parser = createSseParser((data) => {
    let parsed: unknown
    try {
      parsed = JSON.parse(data)
    } catch {
      return // malformed frame: skip rather than abort the whole answer
    }
    const event = toClientEvent(parsed)
    if (event !== null) onEvent(event)
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      parser.push(decoder.decode(value, { stream: true }))
    }
    parser.push(decoder.decode())
    parser.flush()
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(STREAM_INTERRUPTED, '응답 수신 중 연결이 끊어졌습니다.', 0)
  } finally {
    reader.releaseLock()
  }
}
