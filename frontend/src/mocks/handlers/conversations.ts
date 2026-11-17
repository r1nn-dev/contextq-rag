// GET /api/v1/conversations(/{id}) mocks (api-spec 4).

import { CONVERSATION_PAGE_SIZE } from '@/api/conversations'
import { conversations, detailOf, summaryOf } from '../conversations'
import { fail, ok, route } from '../router'
import { authenticate } from './auth'

route('GET', '/conversations', (req) => {
  const auth = authenticate(req)
  if (auth.kind === 'error') return auth.response
  if (auth.kind === 'guest') return fail('AUTH_TOKEN_MISSING', '로그인이 필요합니다.', 401)
  const before = req.query.get('before')
  const size = Math.min(Number(req.query.get('size') ?? CONVERSATION_PAGE_SIZE) || CONVERSATION_PAGE_SIZE, CONVERSATION_PAGE_SIZE)
  const mine = conversations
    .filter((c) => c.ownerId === auth.user.userId && c.messages.length > 0)
    .filter((c) => before === null || c.updatedAt < before)
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
  const items = mine.slice(0, size).map(summaryOf)
  const hasNext = mine.length > size
  return ok({ items, cursor: hasNext ? items[items.length - 1].updatedAt : null, hasNext })
})

route('GET', '/conversations/:id', (req) => {
  const auth = authenticate(req)
  if (auth.kind === 'error') return auth.response
  if (auth.kind === 'guest') return fail('AUTH_TOKEN_MISSING', '로그인이 필요합니다.', 401)
  const conv = conversations.find((c) => String(c.conversationId) === req.params.id)
  // someone else's conversation looks the same as a missing one (INV-14)
  if (conv === undefined || conv.ownerId !== auth.user.userId) {
    return fail('CONVERSATION_NOT_FOUND', '대화를 찾을 수 없습니다.', 404)
  }
  return ok(detailOf(conv))
})
