// Admin API (docs/specs/api-spec.md > 5). JWT + ROLE_ADMIN.

import type { CursorPage } from '@/types/api'
import type {
  AdminLog,
  AdminUser,
  AdminUsersResponse,
  IndexStatusResponse,
  IngestTriggerResponse,
  LogLevel,
} from '@/types/admin'
import { requestJson } from './http'

export function fetchIndexStatus(): Promise<IndexStatusResponse> {
  return requestJson<IndexStatusResponse>('/admin/index/status')
}

/** local·staging only; prod answers FORBIDDEN_IN_PROFILE (api-spec 5.2, policy §9.1). */
export function triggerIngest(sourceKey: string, acceptDrift = false): Promise<IngestTriggerResponse> {
  return requestJson<IngestTriggerResponse>(`/admin/index/ingest/${encodeURIComponent(sourceKey)}`, {
    method: 'POST',
    body: JSON.stringify({ acceptDrift }),
  })
}

export const ADMIN_PAGE_SIZE = 20

/** api-spec 5.3: newest accounts first, email search, cursor page. */
export function fetchUsers(query: string, before: string | null = null): Promise<AdminUsersResponse> {
  const params = new URLSearchParams({ size: String(ADMIN_PAGE_SIZE) })
  if (query.trim() !== '') params.set('query', query.trim())
  if (before !== null) params.set('before', before)
  return requestJson<AdminUsersResponse>(`/admin/users?${params.toString()}`)
}

/** api-spec 5.4: lifts the login lock now; returns the account as in the list. */
export function unlockUser(userId: number): Promise<AdminUser> {
  return requestJson<AdminUser>(`/admin/users/${userId}/unlock`, { method: 'POST' })
}

/** api-spec 5.5: ended answers and guest usage, newest first. */
export function fetchLogs(level: LogLevel | null, before: string | null = null): Promise<CursorPage<AdminLog>> {
  const params = new URLSearchParams({ size: String(ADMIN_PAGE_SIZE) })
  if (level !== null) params.set('level', level)
  if (before !== null) params.set('before', before)
  return requestJson<CursorPage<AdminLog>>(`/admin/logs?${params.toString()}`)
}
