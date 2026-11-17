import { describe, expect, it } from 'vitest'
import { toClientEvent } from './sse'

describe('toClientEvent', () => {
  it('accepts each contract event with its required fields', () => {
    expect(toClientEvent({ event: 'meta', requestId: 'r', conversationId: null, messageId: null })?.event).toBe('meta')
    expect(toClientEvent({ event: 'token', t: 'abc' })?.event).toBe('token')
    expect(toClientEvent({ event: 'done', status: 'COMPLETED' })?.event).toBe('done')
    expect(
      toClientEvent({ event: 'error', code: 'LLM_ERROR', message: 'm', requestId: 'r', partial: true })?.event,
    ).toBe('error')
  })

  it('rejects events missing required fields', () => {
    expect(toClientEvent({ event: 'meta' })).toBeNull()
    expect(toClientEvent({ event: 'token' })).toBeNull()
    expect(toClientEvent({ event: 'error', code: 'X' })).toBeNull()
  })

  it('rejects unknown done status and unknown events', () => {
    expect(toClientEvent({ event: 'done', status: 'PENDING' })).toBeNull()
    expect(toClientEvent({ event: 'progress' })).toBeNull()
    expect(toClientEvent('not an object')).toBeNull()
    expect(toClientEvent(null)).toBeNull()
  })
})
