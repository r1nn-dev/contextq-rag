import { describe, expect, it } from 'vitest'
import type { AdminLog } from '@/types/admin'
import { describeLog } from './adminLog'

const base: AdminLog = {
  at: '2026-11-18T09:00:00Z',
  level: 'ERROR',
  actor: 'USER',
  userId: 2,
  requestId: 'r',
  mode: 'COMPARE',
  status: 'FAILED',
  statusReason: 'LLM_ERROR',
  totalMs: 4120,
  promptTokens: 1240,
  completionTokens: 312,
}

describe('describeLog', () => {
  it('joins mode, status, reason, seconds and tokens', () => {
    expect(describeLog(base)).toBe('COMPARE · FAILED (LLM_ERROR) · 4.1s · 1,240/312 tokens')
  })

  it('leaves out what a guest log does not have', () => {
    const guest: AdminLog = { ...base, actor: 'GUEST', userId: null, requestId: null, mode: 'SINGLE', status: 'COMPLETED', statusReason: null, totalMs: null, promptTokens: null, completionTokens: null }
    expect(describeLog(guest)).toBe('SINGLE · COMPLETED')
  })
})
