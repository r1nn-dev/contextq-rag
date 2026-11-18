// Admin mocks (api-spec 5). The mock behaves like the prod profile for re-ingest,
// so the disabled button state of docs/ui/screenshots/16 can be seen.

import type { AdminLog, AdminUser, IndexStatusResponse } from '@/types/admin'
import { conversations } from '../conversations'
import { MOCK_SOURCES } from '../data'
import { mockState, userById, type MockUser } from '../state'
import { fail, ok, route, type MockRequest } from '../router'
import { authenticate } from './auth'

function requireAdmin(req: MockRequest): Response | null {
  const auth = authenticate(req)
  if (auth.kind === 'error') return auth.response
  if (auth.kind === 'guest') return fail('AUTH_TOKEN_MISSING', '로그인이 필요합니다.', 401)
  if (auth.user.role !== 'ROLE_ADMIN') return fail('FORBIDDEN', '관리자만 접근할 수 있습니다.', 403)
  return null
}

function day(offset: number): string {
  return new Date(Date.now() - offset * 86_400_000).toISOString().slice(0, 10)
}

route('GET', '/admin/index/status', (req) => {
  const denied = requireAdmin(req)
  if (denied !== null) return denied
  const body: IndexStatusResponse = {
    sources: MOCK_SOURCES.sources.map((s, i) => ({
      sourceKey: s.sourceKey,
      displayName: s.displayName,
      enabled: s.enabled,
      activeRun: {
        ingestRunId: 7 + i,
        status: 'ACTIVE',
        commitSha: s.activeRun.commitSha,
        chunkStrategy: 'B',
        chunkCount: s.activeRun.chunkCount,
        prevChunkCount: i === 0 ? 1219 : null,
        embeddingModel: 'text-embedding-3-small',
        embeddingTokens: i === 0 ? 712_000 : 2_150_000,
        embeddingCostUsd: i === 0 ? 0.014 : 0.043,
        ingestDurationMs: i === 0 ? 31_200 : 48_500,
        startedAt: `${s.activeRun.ingestedAt}T03:00:00Z`,
        completedAt: `${s.activeRun.ingestedAt}T03:00:48Z`,
      },
      recentRuns: [
        { ingestRunId: 7 + i, status: 'ACTIVE', startedAt: `${s.activeRun.ingestedAt}T03:00:00Z` },
        { ingestRunId: 5 + i, status: 'SUPERSEDED', startedAt: '2026-10-21T03:00:00Z' },
        ...(i === 1 ? [{ ingestRunId: 3, status: 'FAILED' as const, startedAt: '2026-10-14T03:00:00Z', failureStage: 'VALIDATING' }] : []),
      ],
    })),
    usageSummary: {
      today: { date: day(0), totalMessages: 148, promptTokens: 183_400, completionTokens: 44_200, guestSessions: 32 },
      last7Days: [6, 5, 4, 3, 2, 1, 0].map((d, i) => ({
        date: day(d),
        totalMessages: [95, 120, 88, 132, 160, 141, 148][i],
        promptTokens: [118_000, 150_200, 109_800, 164_000, 199_300, 175_100, 183_400][i],
        completionTokens: [28_500, 36_100, 26_300, 39_800, 48_200, 42_000, 44_200][i],
      })),
    },
  }
  return ok(body)
})

route('POST', '/admin/index/ingest/:sourceKey', (req) => {
  const denied = requireAdmin(req)
  if (denied !== null) return denied
  if (MOCK_SOURCES.sources.every((s) => s.sourceKey !== req.params.sourceKey)) {
    return fail('SOURCE_NOT_FOUND', '존재하지 않는 소스입니다.', 404)
  }
  return fail('FORBIDDEN_IN_PROFILE', '운영 환경에서는 재수집을 실행할 수 없습니다.', 403)
})

// --- users (api-spec 5.3 · 5.4) -----------------------------------------------------------

const DAILY_QUOTA = 100

function adminUserOf(user: MockUser): AdminUser {
  const locked = user.lockedUntil > Date.now()
  const questions = conversations
    .filter((c) => c.ownerId === user.userId)
    .flatMap((c) => c.messages.filter((m) => m.role === 'USER'))
  const today = new Date().toISOString().slice(0, 10)
  return {
    userId: user.userId,
    email: user.email,
    role: user.role,
    status: locked ? 'LOCKED' : 'ACTIVE',
    lockedUntil: locked ? new Date(user.lockedUntil).toISOString() : null,
    createdAt: user.createdAt,
    totalQuestions: questions.length,
    todayQuotaUsed: questions.filter((m) => m.createdAt.startsWith(today)).length,
    dailyQuota: DAILY_QUOTA,
  }
}

route('GET', '/admin/users', (req) => {
  const denied = requireAdmin(req)
  if (denied !== null) return denied
  const query = (req.query.get('query') ?? '').trim().toLowerCase()
  const before = req.query.get('before')
  const size = Math.min(Number(req.query.get('size') ?? 20) || 20, 50)
  const all = [...mockState.users.values()].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
  const matching = all
    .filter((u) => query === '' || u.email.includes(query))
    .filter((u) => before === null || u.createdAt < before)
  const items = matching.slice(0, size).map(adminUserOf)
  const hasNext = matching.length > size
  return ok({
    items,
    cursor: hasNext ? items[items.length - 1].createdAt : null,
    hasNext,
    summary: {
      totalUsers: all.length,
      admins: all.filter((u) => u.role === 'ROLE_ADMIN').length,
      members: all.filter((u) => u.role === 'ROLE_USER').length,
      locked: all.filter((u) => u.lockedUntil > Date.now()).length,
    },
  })
})

route('POST', '/admin/users/:userId/unlock', (req) => {
  const denied = requireAdmin(req)
  if (denied !== null) return denied
  const user = userById(Number(req.params.userId))
  if (user === null) return fail('USER_NOT_FOUND', '사용자를 찾을 수 없습니다.', 404)
  user.failures = 0
  user.lockedUntil = 0
  return ok(adminUserOf(user))
})

// --- request log (api-spec 5.5) -------------------------------------------------------------

const MOCK_LOGS: AdminLog[] = [
  { at: '2026-11-17T09:12:03Z', level: 'INFO', actor: 'USER', userId: 2, requestId: '3f2a9c1e-0000-4000-8000-000000000001', mode: 'SINGLE', status: 'COMPLETED', statusReason: null, totalMs: 4800, promptTokens: 1240, completionTokens: 312 },
  { at: '2026-11-17T09:10:41Z', level: 'WARN', actor: 'GUEST', userId: null, requestId: null, mode: 'SINGLE', status: 'NO_CONTEXT', statusReason: null, totalMs: null, promptTokens: null, completionTokens: null },
  { at: '2026-11-17T09:02:15Z', level: 'ERROR', actor: 'USER', userId: 2, requestId: 'c04e5f72-0000-4000-8000-000000000002', mode: 'COMPARE', status: 'FAILED', statusReason: 'COMPARE_PARSE_ERROR', totalMs: 9100, promptTokens: 2100, completionTokens: 0 },
  { at: '2026-11-17T08:57:30Z', level: 'WARN', actor: 'USER', userId: 2, requestId: '51d9e2b3-0000-4000-8000-000000000003', mode: 'SINGLE', status: 'PARTIAL', statusReason: 'LLM_ERROR', totalMs: 6200, promptTokens: 1180, completionTokens: 112 },
]

route('GET', '/admin/logs', (req) => {
  const denied = requireAdmin(req)
  if (denied !== null) return denied
  const level = req.query.get('level')
  const before = req.query.get('before')
  const size = Math.min(Number(req.query.get('size') ?? 20) || 20, 50)
  if (level !== null && !['INFO', 'WARN', 'ERROR'].includes(level)) {
    return fail('INVALID_REQUEST', '입력값을 확인해주세요.', 400)
  }
  const matching = MOCK_LOGS.filter((l) => level === null || l.level === level).filter(
    (l) => before === null || l.at < before,
  )
  const items = matching.slice(0, size)
  const hasNext = matching.length > size
  return ok({ items, cursor: hasNext ? items[items.length - 1].at : null, hasNext })
})
