// Admin mocks (api-spec 5). The mock behaves like the prod profile for re-ingest,
// so the disabled button state of docs/ui/screenshots/16 can be seen.

import type { IndexStatusResponse } from '@/types/admin'
import { MOCK_SOURCES } from '../data'
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
