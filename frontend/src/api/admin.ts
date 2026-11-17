// Admin API (docs/specs/api-spec.md > 5). JWT + ROLE_ADMIN.

import type { IndexStatusResponse, IngestTriggerResponse } from '@/types/admin'
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
