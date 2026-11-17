// Shared HTTP layer. Components never call fetch directly (frontend/AGENTS.md §2).

import { isRecord, type ApiErrorDetail } from '@/types/api'

/** Same-origin prefix; empty means relative /api paths (frontend/AGENTS.md §1.4). */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export const API_PREFIX = `${API_BASE_URL}/api/v1`

export type Transport = (input: string, init: RequestInit) => Promise<Response>

let transport: Transport = (input, init) => fetch(input, init)

/** Replaces the network layer. Used only by the development mock (VITE_USE_MOCK). */
export function setTransport(next: Transport): void {
  transport = next
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: ApiErrorDetail[]
  readonly retryAfterSec: number | null

  constructor(
    code: string,
    message: string,
    status: number,
    details: ApiErrorDetail[] = [],
    retryAfterSec: number | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
    this.retryAfterSec = retryAfterSec
  }
}

/** Client-side codes for failures that never reached a server response. */
export const NETWORK_ERROR = 'NETWORK_ERROR'
export const STREAM_INTERRUPTED = 'STREAM_INTERRUPTED'

function toDetails(value: unknown): ApiErrorDetail[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (d): d is ApiErrorDetail =>
      isRecord(d) && typeof d.field === 'string' && typeof d.reason === 'string',
  )
}

/**
 * Reads an error response.
 * Accepts the envelope in api-spec 0.3 ({success:false, error:{...}}) and the flat
 * shape in policy 9.2 ({code, message}); the two documents differ on this point.
 */
export async function readApiError(res: Response): Promise<ApiError> {
  const retryHeader = res.headers.get('Retry-After')
  const retryAfter = retryHeader !== null && /^\d+$/.test(retryHeader) ? Number(retryHeader) : null
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // non-JSON body (proxy error page, empty body)
  }
  const source = isRecord(body) && isRecord(body.error) ? body.error : body
  if (isRecord(source) && typeof source.code === 'string') {
    const message = typeof source.message === 'string' ? source.message : '요청을 처리하지 못했습니다.'
    return new ApiError(source.code, message, res.status, toDetails(source.details), retryAfter)
  }
  return new ApiError(`HTTP_${res.status}`, '서버 응답을 처리하지 못했습니다.', res.status, [], retryAfter)
}

/** Sends a request and returns the raw response. Network failures become ApiError. */
export async function send(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await transport(`${API_PREFIX}${path}`, { credentials: 'same-origin', ...init })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(NETWORK_ERROR, '서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.', 0)
  }
}

/** JSON request that unwraps ApiResponse.data. */
export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await send(path, { ...init, headers })
  if (!res.ok) throw await readApiError(res)
  const body: unknown = await res.json()
  if (!isRecord(body) || body.success !== true) {
    throw new ApiError('INVALID_RESPONSE', '서버 응답 형식이 올바르지 않습니다.', res.status)
  }
  return body.data as T
}
