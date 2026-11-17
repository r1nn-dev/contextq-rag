// Chat turns driven by the SSE stream (planning.md > useSseQuery, ADR-003).

import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '@/api/chat'
import { ApiError, STREAM_INTERRUPTED } from '@/api/http'
import type { ChatMode, ChatStreamRequest } from '@/types/chat'
import type { DoneEvent, MetaEvent } from '@/types/sse'

export type TurnPhase = 'waiting' | 'streaming' | 'done' | 'failed'

export interface TurnError {
  code: string
  message: string
  /** true when some answer text arrived before the failure */
  partial: boolean
  retryAfterSec: number | null
}

export interface Turn {
  key: string
  question: string
  request: ChatStreamRequest
  phase: TurnPhase
  meta: MetaEvent | null
  text: string
  done: DoneEvent | null
  error: TurnError | null
}

export interface QuerySelection {
  mode: ChatMode
  sourceKey: string | null
  sourceKeyA: string | null
  sourceKeyB: string | null
}

export interface SseQueryCallbacks {
  onMeta?: (meta: MetaEvent) => void
  onPreStreamError?: (error: ApiError) => void
  /** called once a request settles (not when aborted), e.g. to refresh the conversation list */
  onFinish?: () => void
}

let turnSeq = 0

export function useSseQuery(callbacks: SseQueryCallbacks = {}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const callbacksRef = useRef(callbacks)
  callbacksRef.current = callbacks
  const conversationRef = useRef<number | null>(null)
  conversationRef.current = conversationId

  useEffect(() => () => abortRef.current?.abort(), [])

  const patch = useCallback((key: string, update: (turn: Turn) => Turn) => {
    setTurns((prev) => prev.map((t) => (t.key === key ? update(t) : t)))
  }, [])

  const ask = useCallback(
    async (question: string, selection: QuerySelection) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      turnSeq += 1
      const key = `turn-${turnSeq}`
      const request: ChatStreamRequest = {
        conversationId: conversationRef.current,
        question,
        ...selection,
      }
      setTurns((prev) => [
        ...prev,
        { key, question, request, phase: 'waiting', meta: null, text: '', done: null, error: null },
      ])

      let terminal = false
      let receivedText = false
      try {
        await streamChat(
          request,
          (event) => {
            switch (event.event) {
              case 'meta':
                if (event.conversationId !== null) setConversationId(event.conversationId)
                callbacksRef.current.onMeta?.(event)
                patch(key, (t) => ({ ...t, phase: 'streaming', meta: event }))
                break
              case 'token':
                receivedText = true
                patch(key, (t) => ({ ...t, phase: 'streaming', text: t.text + event.t }))
                break
              case 'done':
                terminal = true
                patch(key, (t) => ({
                  ...t,
                  phase: 'done',
                  done: event,
                  // compare mode carries no tokens; the result arrives in done
                }))
                break
              case 'error':
                terminal = true
                patch(key, (t) => ({
                  ...t,
                  phase: 'failed',
                  error: {
                    code: event.code,
                    message: event.message,
                    partial: event.partial,
                    retryAfterSec: null,
                  },
                }))
                break
            }
          },
          controller.signal,
        )
        if (!terminal) {
          throw new ApiError(STREAM_INTERRUPTED, '응답이 완료되기 전에 연결이 끊어졌습니다.', 0)
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          patch(key, (t) =>
            t.phase === 'done' || t.phase === 'failed'
              ? t
              : {
                  ...t,
                  phase: 'failed',
                  error: { code: 'CANCELLED', message: '답변 생성을 중단했습니다.', partial: receivedText, retryAfterSec: null },
                },
          )
          return
        }
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError(STREAM_INTERRUPTED, '응답을 처리하지 못했습니다.', 0)
        if (!receivedText && apiError.status > 0) callbacksRef.current.onPreStreamError?.(apiError)
        patch(key, (t) => ({
          ...t,
          phase: 'failed',
          error: {
            code: apiError.code,
            message: apiError.message,
            partial: receivedText,
            retryAfterSec: apiError.retryAfterSec,
          },
        }))
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        if (!controller.signal.aborted) callbacksRef.current.onFinish?.()
      }
    },
    [patch],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  /** Starts a fresh conversation, or loads saved turns for an existing one. */
  const reset = useCallback((next: { conversationId: number | null; turns: Turn[] } | null = null) => {
    abortRef.current?.abort()
    setTurns(next?.turns ?? [])
    setConversationId(next?.conversationId ?? null)
  }, [])

  const busy = turns.some((t) => t.phase === 'waiting' || t.phase === 'streaming')

  return { turns, conversationId, busy, ask, stop, reset }
}
