// Builds a text/event-stream Response from a script of timed frames.

import { delay } from './router'

export type MockFrame = { waitMs: number; data: unknown } | { waitMs: number; ping: true }

export function sseResponse(frames: MockFrame[], signal: AbortSignal | null): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for (const frame of frames) {
          await delay(frame.waitMs, signal)
          const text = 'ping' in frame ? ': ping\n\n' : `data: ${JSON.stringify(frame.data)}\n\n`
          controller.enqueue(encoder.encode(text))
        }
        controller.close()
      } catch (err) {
        controller.error(err)
      }
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream; charset=UTF-8' },
  })
}
