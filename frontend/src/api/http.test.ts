import { describe, expect, it } from 'vitest'
import { readApiError } from './http'

function json(body: unknown, status: number, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

describe('readApiError', () => {
  it('reads the common error envelope (api-spec 0.3)', async () => {
    const err = await readApiError(
      json(
        {
          success: false,
          error: { code: 'INVALID_REQUEST', message: '입력값을 확인해주세요.', details: [{ field: 'email', reason: 'bad' }] },
        },
        400,
      ),
    )
    expect(err.code).toBe('INVALID_REQUEST')
    expect(err.status).toBe(400)
    expect(err.details).toEqual([{ field: 'email', reason: 'bad' }])
  })

  it('reads Retry-After seconds', async () => {
    const err = await readApiError(
      json({ success: false, error: { code: 'AUTH_LOCKED', message: 'locked', details: [] } }, 429, { 'Retry-After': '900' }),
    )
    expect(err.retryAfterSec).toBe(900)
  })

  it('drops malformed details entries', async () => {
    const err = await readApiError(
      json({ success: false, error: { code: 'X', message: 'm', details: [{ field: 1 }, 'x'] } }, 400),
    )
    expect(err.details).toEqual([])
  })

  it('falls back to an HTTP code for a non-JSON body', async () => {
    const err = await readApiError(new Response('<html>Bad Gateway</html>', { status: 502 }))
    expect(err.code).toBe('HTTP_502')
    expect(err.status).toBe(502)
  })
})
