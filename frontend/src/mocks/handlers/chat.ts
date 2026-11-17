// POST /api/v1/chat/stream mock.
// Trigger words in the question select a path, so every UI state can be reached by hand:
//   "양자" → NO_CONTEXT (LOW_SIMILARITY) / "오류" → error event after partial tokens
//   "실패" → pre-stream AI_UNAVAILABLE (503)
// Signed-in users get a stored conversation (api-spec 3.1 처리 흐름 2·4·6); guests do not.

import { isRecord } from '@/types/api'
import { QUESTION_MAX_LENGTH } from '@/types/chat'
import { appendTurn, conversations, createConversation, detailOf, type StoredConversation } from '../conversations'
import { answerFixture, findSource, newRequestId, toTokens } from '../data'
import { fail, route } from '../router'
import { GUEST_LIMIT, mockState } from '../state'
import { sseResponse, type MockFrame } from '../stream'
import { authenticate } from './auth'

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
  const user = auth.kind === 'user' ? auth.user : null
  if (body.mode === 'COMPARE' && user === null) {
    return fail('GUEST_MODE_NOT_ALLOWED', '비교 모드는 로그인 후 이용할 수 있습니다.', 403)
  }

  // an existing conversation fixes mode and version (INV-10)
  let conv: StoredConversation | null = null
  if (typeof body.conversationId === 'number') {
    conv = conversations.find((c) => c.conversationId === body.conversationId && c.ownerId === user?.userId) ?? null
    if (conv === null) return fail('CONVERSATION_NOT_FOUND', '대화를 찾을 수 없습니다.', 404)
    if (detailOf(conv).status === 'READ_ONLY') {
      return conv.messages.length >= 100
        ? fail('CONVERSATION_FULL', '이 대화는 메시지 한도에 도달했습니다. 새 대화를 시작해주세요.', 409)
        : fail('SOURCE_UNAVAILABLE', '더 이상 질문할 수 없는 버전입니다.', 409)
    }
  }
  const source = findSource(conv?.sourceKey ?? (typeof body.sourceKey === 'string' ? body.sourceKey : null))
  if (source === null) {
    return fail('SOURCE_NOT_FOUND', '존재하지 않는 버전입니다.', 404)
  }
  if (user === null && mockState.guestUsed >= GUEST_LIMIT) {
    return fail('GUEST_QUOTA_EXCEEDED', '게스트 질문 5회를 모두 사용했습니다.', 429)
  }
  if (question.includes('실패')) {
    return fail('AI_UNAVAILABLE', 'AI 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.', 503)
  }
  if (user === null) mockState.guestUsed += 1

  const requestId = newRequestId()
  const noContext = question.includes('양자')
  const broken = question.includes('오류')
  const fixture = answerFixture(source.sourceKey)
  const tokens = toTokens(fixture.answer)
  const cut = broken ? Math.floor(tokens.length / 3) : tokens.length

  let conversationId: number | null = null
  let messageId: number | null = null
  let rewrittenQuery: string | null = null
  if (user !== null) {
    conv ??= createConversation(user.userId, 'SINGLE', { sourceKey: source.sourceKey, sourceKeyA: null, sourceKeyB: null })
    messageId = appendTurn(conv, question, {
      status: noContext ? 'NO_CONTEXT' : broken ? 'FAILED' : 'COMPLETED',
      statusReason: noContext ? 'LOW_SIMILARITY' : broken ? 'LLM_ERROR' : null,
      content: noContext ? '' : tokens.slice(0, cut).join(''),
      requestId,
      sources: noContext ? [] : fixture.sources,
    })
    conversationId = conv.conversationId
    const saved = conv.messages.find((m) => m.messageId === messageId)
    rewrittenQuery = saved !== undefined && saved.role === 'ASSISTANT' ? saved.rewrittenQuery : null
  }

  const meta = {
    event: 'meta',
    requestId,
    conversationId,
    messageId,
    sourceKey: source.sourceKey,
    ingestRunId: 7,
    commitSha: source.activeRun.commitSha,
    ingestedAt: source.activeRun.ingestedAt,
    rewrittenQuery,
  }
  const frames: MockFrame[] = []

  if (noContext) {
    frames.push({ waitMs: 500, data: { ...meta, noContext: true, sources: [] } })
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

  frames.push({ waitMs: 600, data: { ...meta, noContext: false, sources: fixture.sources } })
  frames.push({ waitMs: 900, ping: true })
  tokens.slice(0, cut).forEach((t) => frames.push({ waitMs: TOKEN_WAIT_MS, data: { event: 'token', t } }))

  if (broken) {
    frames.push({
      waitMs: 200,
      data: { event: 'error', code: 'LLM_ERROR', message: 'LLM 오류가 발생했습니다. 다시 질문해주세요.', requestId, partial: true },
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
