// GET /api/v1/sources (docs/specs/api-spec.md > 2.1)

import type { SourcesResponse } from '@/types/sources'
import { requestJson } from './http'

export function fetchSources(): Promise<SourcesResponse> {
  return requestJson<SourcesResponse>('/sources')
}
