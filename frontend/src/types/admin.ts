// GET /api/v1/admin/index/status, POST /api/v1/admin/index/ingest/{sourceKey}
// (docs/specs/api-spec.md > 5)

export type IngestRunStatus =
  | 'PENDING'
  | 'COLLECTING'
  | 'PROCESSING'
  | 'EMBEDDING'
  | 'VALIDATING'
  | 'READY'
  | 'ACTIVE'
  | 'RESTORING'
  | 'SUPERSEDED'
  | 'PURGED'
  | 'FAILED'

export interface AdminActiveRun {
  ingestRunId: number
  status: IngestRunStatus
  commitSha: string
  chunkStrategy: string
  chunkCount: number
  prevChunkCount: number | null
  embeddingModel: string
  embeddingTokens: number
  embeddingCostUsd: number
  ingestDurationMs: number
  startedAt: string
  completedAt: string
}

export interface RecentRun {
  ingestRunId: number
  status: IngestRunStatus
  /** null for a run that has not started collecting (api-spec 5.1 응답 규칙) */
  startedAt: string | null
  failureStage?: string
}

export interface AdminSourceStatus {
  sourceKey: string
  displayName: string
  enabled: boolean
  activeRun: AdminActiveRun | null
  recentRuns: RecentRun[]
}

export interface DailyUsage {
  date: string
  totalMessages: number
  promptTokens: number
  completionTokens: number
  guestSessions?: number
}

export interface IndexStatusResponse {
  sources: AdminSourceStatus[]
  usageSummary: {
    today: DailyUsage
    last7Days: DailyUsage[]
  }
}

export interface IngestTriggerResponse {
  ingestRunId: number
}

// GET /api/v1/admin/users, POST /api/v1/admin/users/{userId}/unlock (api-spec 5.3 · 5.4)

export type AdminUserStatus = 'ACTIVE' | 'LOCKED'

export interface AdminUser {
  userId: number
  email: string
  role: 'ROLE_USER' | 'ROLE_ADMIN'
  /** LOCKED while the 15-minute login lock holds (policy §1.2) */
  status: AdminUserStatus
  lockedUntil: string | null
  createdAt: string
  totalQuestions: number
  /** today's (KST) daily quota use; compare questions count 2 */
  todayQuotaUsed: number
  dailyQuota: number
}

export interface AdminUsersResponse {
  items: AdminUser[]
  cursor: string | null
  hasNext: boolean
  summary: { totalUsers: number; admins: number; members: number; locked: number }
}

// GET /api/v1/admin/logs (api-spec 5.5)

export type LogLevel = 'INFO' | 'WARN' | 'ERROR'

export interface AdminLog {
  at: string
  level: LogLevel
  actor: 'USER' | 'GUEST'
  userId: number | null
  requestId: string | null
  mode: 'SINGLE' | 'COMPARE'
  status: 'COMPLETED' | 'PARTIAL' | 'NO_CONTEXT' | 'FAILED'
  statusReason: string | null
  totalMs: number | null
  promptTokens: number | null
  completionTokens: number | null
}
