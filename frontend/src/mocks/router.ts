// In-browser mock of the backend REST API, enabled only with VITE_USE_MOCK=true.
// Responses follow docs/specs/api-spec.md so the real API and SSE code paths run unchanged.

import type { Transport } from '@/api/http'

export interface MockRequest {
  method: string
  path: string
  query: URLSearchParams
  headers: Headers
  body: unknown
  signal: AbortSignal | null
  params: Record<string, string>
}

export type MockHandler = (req: MockRequest) => Response | Promise<Response>

interface Route {
  method: string
  pattern: RegExp
  keys: string[]
  handler: MockHandler
}

const routes: Route[] = []

/** Registers a handler. Path segments starting with ':' are captured as params. */
export function route(method: string, path: string, handler: MockHandler): void {
  const keys: string[] = []
  const source = path
    .split('/')
    .map((segment) => {
      if (segment.startsWith(':')) {
        keys.push(segment.slice(1))
        return '([^/]+)'
      }
      return segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    })
    .join('/')
  routes.push({ method, pattern: new RegExp(`^${source}$`), keys, handler })
}

export function ok<T>(data: T, status = 200, message: string | null = null): Response {
  return new Response(JSON.stringify({ success: true, message, data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function fail(
  code: string,
  message: string,
  status: number,
  extra: { details?: { field: string; reason: string }[]; retryAfterSec?: number } = {},
): Response {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (extra.retryAfterSec !== undefined) headers.set('Retry-After', String(extra.retryAfterSec))
  return new Response(
    JSON.stringify({ success: false, error: { code, message, details: extra.details ?? [] } }),
    { status, headers },
  )
}

export function delay(ms: number, signal: AbortSignal | null = null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

async function readBody(init: RequestInit): Promise<unknown> {
  if (typeof init.body !== 'string' || init.body === '') return null
  try {
    return JSON.parse(init.body)
  } catch {
    return null
  }
}

export const mockFetch: Transport = async (input, init) => {
  const url = new URL(input, window.location.origin)
  const path = url.pathname.replace(/^.*\/api\/v1/, '')
  const method = (init.method ?? 'GET').toUpperCase()
  const body = await readBody(init)
  // simulated network latency for non-stream calls
  await delay(150, init.signal ?? null)

  for (const r of routes) {
    if (r.method !== method) continue
    const match = r.pattern.exec(path)
    if (match === null) continue
    const params: Record<string, string> = {}
    r.keys.forEach((key, i) => {
      params[key] = decodeURIComponent(match[i + 1])
    })
    return r.handler({
      method,
      path,
      query: url.searchParams,
      headers: new Headers(init.headers),
      body,
      signal: init.signal ?? null,
      params,
    })
  }
  return fail('NOT_FOUND', `목 응답이 없는 경로입니다: ${method} ${path}`, 404)
}
