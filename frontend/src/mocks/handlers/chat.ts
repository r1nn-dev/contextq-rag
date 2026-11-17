// POST /api/v1/chat/stream mock.
// Trigger words in the question select a path, so every UI state can be reached by hand:
//   "양자" → NO_CONTEXT (LOW_SIMILARITY) / "오류" → error event after partial tokens
//   "실패" → pre-stream AI_UNAVAILABLE (503)

import { isRecord } from '@/types/api'
import { QUESTION_MAX_LENGTH } from '@/types/chat'
import { answerFixture, findSource, newRequestId, toTokens } from '../data'
import { fail, route } from '../router'
import { GUEST_LIMIT, mockState } from '../state'
import { authenticate } from './auth'
import { sseResponse, type MockFrame } from '../stream'

const TOKEN_WAIT_MS = 25

route('POST', '/chat/stream', (req) => {
  const body = isRecord(req.body) ? req.body : {}
  const question = typeof body.question === 'string' ? body.question.trim() : ''
  if (question.length < 1 || question.length > QUESTION_MAX_LENGTH) {
    return fail('INVALID_REQUEST', '입력값을 확인해주세요.', 400, {
      details: [{ field: 'question', reason: `질문은 1~${QUESTION_MAX_LENGTH}자로 입력해주세요.` }],
    })
  }
  const auth = authenticate(req)
  if (auth.kind === 'error') return auth.response
  const isGuest = auth.kind === 'guest'
  if (body.mode === 'COMPARE' && isGuest) {
    return fail('GUEST_MODE_NOT_ALLOWED', '비교 모드는 로그인 후 이용할 수 있습니다.', 403)
  }
  const source = findSource(typeof body.sourceKey === 'string' ? body.sourceKey : null)
  if (source === null) {
    return fail('SOURCE_NOT_FOUND', '존재하지 않는 버전입니다.', 404)
  }
  if (isGuest && mockState.guestUsed >= GUEST_LIMIT) {
    return fail('GUEST_QUOTA_EXCEEDED', '게스트 질문 5회를 모두 사용했습니다.', 429)
  }
  if (question.includes('실패')) {
    return fail('AI_UNAVAILABLE', 'AI 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.', 503)
  }
  if (isGuest) mockState.guestUsed += 1

  const requestId = newRequestId()
  const snapshot = {
    sourceKey: source.sourceKey,
    ingestRunId: 7,
    commitSha: source.activeRun.commitSha,
    ingestedAt: source.activeRun.ingestedAt,
  }
  const frames: MockFrame[] = []

  if (question.includes('양자')) {
    frames.push({
      waitMs: 500,
      data: {
        event: 'meta',
        requestId,
        conversationId: null,
        messageId: null,
        ...snapshot,
        rewrittenQuery: null,
        noContext: true,
        sources: [],
      },
    })
    frames.push({
      waitMs: 100,
      data: {
        event: 'done',
        status: 'NO_CONTEXT',
        statusReason: 'LOW_SIMILARITY',
        finishReason: null,
        usage: null,
        latency: { rewriteMs: 0, embedMs: 80, retrieveMs: 120, ttftMs: null, totalMs: 260 },
      },
    })
    return sseResponse(frames, req.signal)
  }

  const fixture = answerFixture(source.sourceKey)
  frames.push({
    waitMs: 600,
    data: {
      event: 'meta',
      requestId,
      conversationId: null,
      messageId: null,
      ...snapshot,
      rewrittenQuery: null,
      noContext: false,
      sources: fixture.sources,
    },
  })
  frames.push({ waitMs: 900, ping: true })

  const tokens = toTokens(fixture.answer)
  const cut = question.includes('오류') ? Math.floor(tokens.length / 3) : tokens.length
  tokens.slice(0, cut).forEach((t) => frames.push({ waitMs: TOKEN_WAIT_MS, data: { event: 'token', t } }))

  if (cut < tokens.length) {
    frames.push({
      waitMs: 200,
      data: {
        event: 'error',
        code: 'LLM_ERROR',
        message: 'LLM 오류가 발생했습니다. 다시 질문해주세요.',
        requestId,
        partial: true,
      },
    })
    return sseResponse(frames, req.signal)
  }

  frames.push({
    waitMs: 100,
    data: {
      event: 'done',
      status: 'COMPLETED',
      statusReason: null,
      finishReason: 'stop',
      usage: { prompt: 1240, completion: 312 },
      latency: { rewriteMs: 0, embedMs: 80, retrieveMs: 120, ttftMs: 1500, totalMs: 4800 },
      invalidCitations: fixture.sources.length < 3 ? [] : [7],
    },
  })
  return sseResponse(frames, req.signal)
})
