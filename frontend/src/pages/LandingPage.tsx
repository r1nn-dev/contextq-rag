import { Link } from 'react-router-dom'
import { Logo } from '@/components/common/Logo'
import { frameworkName, useSources } from '@/hooks/useSources'
import '@/styles/landing.css'

const FEATURES = [
  {
    icon: '🔀',
    title: '버전 격리 컬렉션',
    body: '버전별 공식 문서를 별도 컬렉션으로 분리합니다. 버전 간 오염 없이 질문하는 버전에 맞는 답변을 제공합니다.',
    tag: 'RAG 아키텍처',
    tagClass: 'tone-c',
  },
  {
    icon: '📎',
    title: '출처 추적 (Source Attribution)',
    body: '모든 답변에 참조한 공식 문서 링크를 첨부합니다. 답변 생성 전에 출처를 먼저 보여 줘 근거를 바로 확인할 수 있습니다.',
    tag: '신뢰성',
    tagClass: 'tag-ok',
  },
  {
    icon: '⚠️',
    title: 'NO_CONTEXT 감지',
    body: '관련 문서의 유사도가 임계값보다 낮으면 LLM을 호출하지 않고 "관련 문서 없음"을 반환합니다. 근거 없는 답변을 원천 차단합니다.',
    tag: '정확도',
    tagClass: 'tag-warn',
  },
  {
    icon: '⚖️',
    title: '비교 모드 (Compare Mode)',
    body: '같은 질문에 대한 두 버전의 답변을 나란히 비교합니다. 마이그레이션 작업 시 버전 간 차이를 한눈에 파악할 수 있습니다.',
    tag: '마이그레이션',
    tagClass: 'tone-c',
  },
] as const

export function LandingPage(): JSX.Element {
  const { sources } = useSources()
  const framework = frameworkName(sources) ?? '기술 문서'
  const labels = sources.map((s) => s.versionLabel).join(' · ')
  const demoLabel = sources.length > 0 ? sources[sources.length - 1].versionLabel : '…'

  return (
    <div className="landing">
      <nav className="landing-nav">
        <Link to="/" className="brand">
          <Logo />
        </Link>
        <span className="spacer" />
        <a href="#features" className="btn btn-ghost btn-sm">
          기능 소개
        </a>
        <Link to="/login" className="btn btn-outline btn-sm">
          로그인
        </Link>
        <Link to="/signup" className="btn btn-primary btn-sm">
          회원가입
        </Link>
      </nav>

      <section className="hero">
        <div>
          <span className="hero-badge">🔀 Version-Aware RAG</span>
          <h1>
            {framework} 버전 충돌,
            <br />더 이상 <em>삽질</em>하지 마세요
          </h1>
          <p className="hero-lead">
            {labels !== '' ? `${labels} ` : ''}공식 문서를 버전별로 격리하여
            <br />
            정확한 답변을 제공하는 AI 개발 학습 플랫폼
          </p>
          <div className="hero-actions">
            <Link to="/chat" className="btn btn-primary btn-lg">
              지금 시작하기
            </Link>
            <a href="#features" className="btn btn-outline btn-lg">
              더 알아보기 →
            </a>
          </div>
          <div className="hero-checks">
            <span>✓ 게스트 5회 무료</span>
            <span>✓ 출처 문서 첨부</span>
            <span>✓ 버전 비교 모드</span>
          </div>
        </div>

        <div className="terminal" aria-hidden="true">
          <div className="terminal-bar">
            <i />
            <i />
            <i />
            ContextQ — {framework} Q&amp;A
          </div>
          <div className="terminal-body">
            <div>
              <span className="dim">버전 선택 →</span> <span className="tag tone-b">{demoLabel}</span>
            </div>
            <div>
              <span className="k">질문:</span> run()과 invoke() 메서드의 차이가 뭐야?
            </div>
            <div className="dim">── 참고 문서 로드 중 ──</div>
            <div>📄 LCEL Primitives — Invoke</div>
            <div>📄 Migration Guide — run() to invoke()</div>
            <div>📄 BaseLLM API Reference</div>
            <div>
              <span className="k">답변:</span> invoke()는 Runnable 표준 메서드로…
            </div>
            <span className="terminal-cursor" />
          </div>
        </div>
      </section>

      <section className="features" id="features">
        <div className="eyebrow">CORE FEATURES</div>
        <h2>왜 ContextQ인가?</h2>
        <p className="muted">{framework} 버전 혼용으로 발생하는 혼란을 구조적으로 해결합니다</p>
        <div className="features-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="feature-card">
              <div className="feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
              <span className={`tag tag-plain ${f.tagClass}`}>{f.tag}</span>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
