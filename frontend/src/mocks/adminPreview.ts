// Preview data for admin screens that have no API in docs/specs/api-spec.md yet
// (user management, system log). Loaded by those pages only in mock mode.

import type { LogPreviewRow, UserPreviewRow } from '@/types/admin'

export const USER_PREVIEW: UserPreviewRow[] = [
  { email: 'admin@contextq.dev', joinedAt: '2026-10-01', role: 'admin', totalQuestions: null, quota: '무제한' },
  { email: 'user1@example.com', joinedAt: '2026-10-15', role: 'user', totalQuestions: 142, quota: '일 100회' },
  { email: 'dev.kim@example.com', joinedAt: '2026-10-18', role: 'user', totalQuestions: 87, quota: '일 100회' },
  { email: 'backend.lee@example.com', joinedAt: '2026-10-22', role: 'user', totalQuestions: 204, quota: '일 100회' },
  { email: 'student.park@example.com', joinedAt: '2026-10-30', role: 'user', totalQuestions: 31, quota: '일 100회' },
  { email: '게스트 세션 #a91f', joinedAt: '2026-11-01', role: 'guest', totalQuestions: 5, quota: '5회' },
]

export const LOG_PREVIEW: LogPreviewRow[] = [
  { at: '2026-11-17T09:12:03Z', level: 'INFO', requestId: '3f2a9c1e-…', message: 'chat stream completed (SINGLE, 4.8s)' },
  { at: '2026-11-17T09:10:41Z', level: 'WARN', requestId: '8b17d0aa-…', message: 'NO_CONTEXT (LOW_SIMILARITY)' },
  { at: '2026-11-17T09:02:15Z', level: 'ERROR', requestId: 'c04e5f72-…', message: 'LLM_ERROR after 112 tokens (PARTIAL)' },
  { at: '2026-11-17T08:57:30Z', level: 'INFO', requestId: '51d9e2b3-…', message: 'refresh token rotated' },
]
