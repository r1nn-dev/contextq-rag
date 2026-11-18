// Guest rewrite context sent as `history` (docs/specs/api-spec.md > 3.1 history 규칙, policy §5.2).
// Logged-in users never send it: their history comes from the server DB.

import type { HistoryItem } from '@/types/chat'
import type { Turn } from './useSseQuery'

/** 3 turns (policy §5.2 참조 범위). */
export const HISTORY_TURNS = 3
/** Per-message limit the server re-checks (api-spec 3.1). */
export const HISTORY_MAX_CHARS = 2000

/** An answer the rewrite can use: COMPLETED or PARTIAL text. FAILED and the NO_CONTEXT notice are left out. */
function usableAnswer(turn: Turn): string | null {
  if (turn.text.trim() === '') return null
  if (turn.phase === 'done') {
    const status = turn.done?.status
    return status === 'COMPLETED' || status === 'PARTIAL' ? turn.text : null
  }
  // a stream that failed after some text is stored as PARTIAL (policy §10.2)
  if (turn.phase === 'failed' && turn.error?.partial === true) return turn.text
  return null
}

/** Newest 3 finished turns, oldest first; the question of an excluded answer stays. */
export function guestHistory(turns: readonly Turn[]): HistoryItem[] {
  const finished = turns.filter((t) => t.phase === 'done' || t.phase === 'failed')
  const history: HistoryItem[] = []
  for (const turn of finished.slice(-HISTORY_TURNS)) {
    history.push({ role: 'user', content: turn.question.slice(0, HISTORY_MAX_CHARS) })
    const answer = usableAnswer(turn)
    if (answer !== null) history.push({ role: 'assistant', content: answer.slice(0, HISTORY_MAX_CHARS) })
  }
  return history
}
