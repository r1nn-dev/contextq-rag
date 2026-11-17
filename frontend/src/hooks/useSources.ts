// Version catalog loaded once at app start (api-spec 2.1 > 프론트 계약).

import { createContext, useContext } from 'react'
import type { ComparePair, GuestUsage, Source } from '@/types/sources'

export interface SourcesState {
  status: 'loading' | 'ready' | 'error'
  sources: Source[]
  comparePairs: ComparePair[]
  /** Server guest usage at load time; null when logged in or not loaded yet. */
  guest: GuestUsage | null
  errorMessage: string | null
  reload: () => void
}

export const SourcesContext = createContext<SourcesState | null>(null)

export function useSources(): SourcesState {
  const value = useContext(SourcesContext)
  if (value === null) throw new Error('useSources must be used inside SourcesProvider')
  return value
}

export type VersionTone = 'tone-a' | 'tone-b' | 'tone-c'

/**
 * Colour slot by catalog position, so styling never branches on a version string (UI-01).
 * The first two catalog entries map to the two mockup colours (amber, green).
 */
export function versionTone(sources: Source[], sourceKey: string | null | undefined): VersionTone {
  const index = sources.findIndex((s) => s.sourceKey === sourceKey)
  if (index === 0) return 'tone-a'
  if (index === 1) return 'tone-b'
  return 'tone-c'
}

export function findSource(sources: Source[], sourceKey: string | null | undefined): Source | null {
  return sources.find((s) => s.sourceKey === sourceKey) ?? null
}

/** Framework display name derived from the catalog ("LangChain v0.3" → "LangChain"). */
export function frameworkName(sources: Source[]): string | null {
  const first = sources[0]
  if (first === undefined) return null
  const name = first.displayName.replace(first.versionLabel, '').trim()
  return name !== '' ? name : first.framework
}

/** Policy §3.2: show the version with the first 7 SHA characters and the ingest date. */
export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 7) : '-------'
}
