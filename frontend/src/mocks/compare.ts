// Compare-mode mock stream: meta (A/B sources) → done (compareResult), no tokens
// (api-spec 부록 B.2·B.4, policy §5.6). "한쪽" in the question makes side A lack evidence.

import type { ChatMode } from '@/types/chat'
import type { CompareResult, SseSource } from '@/types/sse'
import { appendTurn, createConversation, type StoredConversation } from './conversations'
import { answerFixture, MOCK_SOURCES, newRequestId } from './data'
import type { MockUser } from './state'
import { sseResponse, type MockFrame } from './stream'

function prefixed(sources: SseSource[], prefix: 'A' | 'B'): SseSource[] {
  return sources.map((s, i) => ({ ...s, rank: `${prefix}${i + 1}` }))
}

function buildResult(oneSided: boolean): CompareResult {
  return {
    version_a: oneSided
      ? { summary: '', citations: [], no_evidence: true }
      : {
          summary: [
            '체인은 `__call__`이나 **run()** 메서드로 실행했습니다. [A1]',
            '',
            '```python',
            'from langchain.chains import LLMChain',
            '',
            'chain = LLMChain(llm=llm, prompt=prompt)',
            'result = chain.run("Hello")',
            '```',
            '',
            '`invoke()`도 일부 지원되었지만 반환 형식이 일관되지 않았습니다. [A2]',
          ].join('\n'),
          citations: ['A1', 'A2'],
          no_evidence: false,
        },
    version_b: {
      summary: [
        '모든 Runnable 객체는 **invoke()**를 사용합니다. [B1]',
        '',
        '```python',
        'chain = ChatPromptTemplate.from_template("{input}") | llm',
        'result = chain.invoke({"input": "Hello"})',
        '```',
        '',
        '`run()`은 deprecated 되었고 LCEL 파이프라인에서는 `invoke()`가 표준입니다. [B2][B3]',
      ].join('\n'),
      citations: ['B1', 'B2', 'B3'],
      no_evidence: false,
    },
    // policy §5.6: changes are listed only when both sides have evidence
    changes: oneSided
      ? []
      : [
          { aspect: '체인 실행 메서드', a: '`chain.run()` / `chain()`', b: '`chain.invoke()`', citations_a: ['A1'], citations_b: ['B1'] },
          { aspect: '체인 구성 방식', a: '`LLMChain(llm, prompt)` 클래스', b: '`prompt | llm` 파이프 연산자(LCEL)', citations_a: ['A1'], citations_b: ['B2'] },
          { aspect: '반환 형식', a: '체인마다 다름 (문자열 또는 dict)', b: 'Runnable 출력 타입으로 일관', citations_a: ['A2'], citations_b: ['B3'] },
        ],
  }
}

export function compareStream(
  user: MockUser,
  conv: StoredConversation | null,
  question: string,
  signal: AbortSignal | null,
  mode: ChatMode = 'COMPARE',
): Response {
  const [a, b] = MOCK_SOURCES.sources
  const keyA = conv?.sourceKeyA ?? a.sourceKey
  const keyB = conv?.sourceKeyB ?? b.sourceKey
  const requestId = newRequestId()
  const noContext = question.includes('양자')
  const oneSided = question.includes('한쪽')
  const sourcesA = oneSided ? [] : prefixed(answerFixture(keyA).sources, 'A')
  const sourcesB = prefixed(answerFixture(keyB).sources, 'B')
  const sources = noContext ? [] : [...sourcesA, ...sourcesB]
  const result = noContext ? null : buildResult(oneSided)

  const target = conv ?? createConversation(user.userId, mode, { sourceKey: null, sourceKeyA: keyA, sourceKeyB: keyB })
  const messageId = appendTurn(target, question, {
    status: noContext ? 'NO_CONTEXT' : 'COMPLETED',
    statusReason: noContext ? 'LOW_SIMILARITY' : null,
    content: result === null ? '' : `${result.version_a.summary}\n\n${result.version_b.summary}`,
    requestId,
    sources,
    compareResult: result,
  })

  const frames: MockFrame[] = [
    {
      waitMs: 700,
      data: {
        event: 'meta',
        requestId,
        conversationId: target.conversationId,
        messageId,
        sourceKeyA: keyA,
        sourceKeyB: keyB,
        ingestRunIdA: 7,
        ingestRunIdB: 8,
        commitShaA: a.activeRun.commitSha,
        commitShaB: b.activeRun.commitSha,
        ingestedAtA: a.activeRun.ingestedAt,
        ingestedAtB: b.activeRun.ingestedAt,
        rewrittenQuery: null,
        noContext,
        sources,
      },
    },
    { waitMs: 1200, ping: true },
    {
      waitMs: 1300,
      data: {
        event: 'done',
        status: noContext ? 'NO_CONTEXT' : 'COMPLETED',
        statusReason: noContext ? 'LOW_SIMILARITY' : null,
        finishReason: noContext ? null : 'stop',
        usage: noContext ? null : { prompt: 2480, completion: 610 },
        latency: { rewriteMs: 0, embedMs: 90, retrieveMs: 150, ttftMs: null, totalMs: 3200 },
        invalidCitations: [],
        compareResult: result,
      },
    },
  ]
  return sseResponse(frames, signal)
}

// seed: one compare conversation for the demo account
const seeded = createConversation(2, 'COMPARE', {
  sourceKey: null,
  sourceKeyA: MOCK_SOURCES.sources[0].sourceKey,
  sourceKeyB: MOCK_SOURCES.sources[1].sourceKey,
}, new Date(Date.now() - 50 * 3_600_000).toISOString())
const seedResult = buildResult(false)
appendTurn(
  seeded,
  'invoke() 메서드의 사용법을 알려줘',
  {
    status: 'COMPLETED',
    statusReason: null,
    content: seedResult.version_a.summary,
    requestId: newRequestId(),
    sources: [
      ...prefixed(answerFixture(MOCK_SOURCES.sources[0].sourceKey).sources, 'A'),
      ...prefixed(answerFixture(MOCK_SOURCES.sources[1].sourceKey).sources, 'B'),
    ],
    compareResult: seedResult,
  },
  seeded.updatedAt,
)
