import { describe, expect, it } from 'vitest'
import type { DoneEvent } from '@/types/sse'
import { guestHistory } from './guestHistory'
import type { Turn } from './useSseQuery'

function turn(question: string, text: string, overrides: Partial<Turn> = {}): Turn {
  return {
    key: question,
    question,
    request: { conversationId: null, question, mode: 'SINGLE', sourceKey: 'langchain_v03', sourceKeyA: null, sourceKeyB: null },
    phase: 'done',
    meta: null,
    text,
    done: { event: 'done', status: 'COMPLETED' } as DoneEvent,
    error: null,
    ...overrides,
  }
}

describe('guestHistory', () => {
  it('keeps the newest three finished turns, oldest first', () => {
    const turns = [turn('q1', 'a1'), turn('q2', 'a2'), turn('q3', 'a3'), turn('q4', 'a4')]

    expect(guestHistory(turns)).toEqual([
      { role: 'user', content: 'q2' },
      { role: 'assistant', content: 'a2' },
      { role: 'user', content: 'q3' },
      { role: 'assistant', content: 'a3' },
      { role: 'user', content: 'q4' },
      { role: 'assistant', content: 'a4' },
    ])
  })

  it('drops failed and NO_CONTEXT answers but keeps their questions', () => {
    const turns = [
      turn('q1', '', { phase: 'failed', done: null, error: { code: 'AI_UNAVAILABLE', message: 'm', partial: false, retryAfterSec: null } }),
      turn('q2', '근거 부족', { done: { event: 'done', status: 'NO_CONTEXT' } as DoneEvent }),
      turn('q3', '부분 답', { phase: 'failed', done: null, error: { code: 'LLM_ERROR', message: 'm', partial: true, retryAfterSec: null } }),
    ]

    expect(guestHistory(turns)).toEqual([
      { role: 'user', content: 'q1' },
      { role: 'user', content: 'q2' },
      { role: 'user', content: 'q3' },
      { role: 'assistant', content: '부분 답' },
    ])
  })

  it('ignores the turn still streaming and cuts long answers to 2,000 chars', () => {
    const turns = [turn('q1', 'a'.repeat(2500)), turn('q2', '', { phase: 'streaming', done: null })]

    const history = guestHistory(turns)

    expect(history).toHaveLength(2)
    expect(history[1]?.content).toHaveLength(2000)
  })

  it('is empty for the first question', () => {
    expect(guestHistory([])).toEqual([])
  })
})
