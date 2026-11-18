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

/**
 * Preview-only rows for the user management screen (docs/ui/screenshots/17).
 * api-spec has no user list API yet; the shape here is a UI placeholder, not a contract.
 */
export interface UserPreviewRow {
  email: string
  joinedAt: string
  role: 'admin' | 'user' | 'guest'
  totalQuestions: number | null
  quota: string
}

export interface LogPreviewRow {
  at: string
  level: 'INFO' | 'WARN' | 'ERROR'
  requestId: string
  message: string
}
