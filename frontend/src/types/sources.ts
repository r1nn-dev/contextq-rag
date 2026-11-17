// GET /api/v1/sources (docs/specs/api-spec.md > 2.1)

export interface ActiveRun {
  commitSha: string
  ingestedAt: string
  chunkCount: number
}

export interface Source {
  sourceKey: string
  framework: string
  versionLabel: string
  displayName: string
  enabled: boolean
  activeRun: ActiveRun
}

export interface ComparePair {
  compareEnabled: boolean
  sourceKeyA: string
  sourceKeyB: string
}

export interface SourcesResponse {
  sources: Source[]
  comparePairs: ComparePair[]
}
