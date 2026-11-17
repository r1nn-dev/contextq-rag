// Sidebar "최근 대화" (docs/ui/screenshots/06, 14).

import { Link, useLocation } from 'react-router-dom'
import { Icon } from '@/components/common/Icon'
import { useConversationList } from '@/hooks/useConversationList'
import { useSources, versionTone } from '@/hooks/useSources'
import type { ConversationSummary } from '@/types/conversation'
import { formatRelative } from '@/utils/format'

const RECENT_COUNT = 4

export function ConversationTag({ item }: { item: ConversationSummary }): JSX.Element {
  const { sources } = useSources()
  if (item.mode === 'COMPARE') return <span className="tag tone-c">비교</span>
  return <span className={`tag ${versionTone(sources, item.sourceKey)}`}>{item.versionLabel}</span>
}

export function RecentConversations(): JSX.Element {
  const { status, items } = useConversationList()
  const { pathname } = useLocation()
  const recent = items.slice(0, RECENT_COUNT)

  return (
    <>
      <div className="sidebar-section-label">최근 대화</div>
      {status === 'loading' && <div className="sidebar-note faint">불러오는 중…</div>}
      {status === 'error' && <div className="sidebar-note faint">목록을 불러오지 못했습니다.</div>}
      {status === 'ready' && recent.length === 0 && <div className="sidebar-note faint">아직 대화가 없습니다.</div>}
      <nav className="conv-list" aria-label="최근 대화">
        {recent.map((item) => {
          const to = `/chat/${item.conversationId}`
          return (
            <Link key={item.conversationId} to={to} className={pathname === to ? 'conv-item active' : 'conv-item'}>
              <ConversationTag item={item} />
              <span className="conv-title">{item.title}</span>
              <span className="conv-time">{formatRelative(item.updatedAt)}</span>
            </Link>
          )
        })}
      </nav>
      <Link to="/history" className="conv-more">
        이력 전체 보기 <Icon name="arrowRight" size={12} />
      </Link>
    </>
  )
}
