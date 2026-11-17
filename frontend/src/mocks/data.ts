// Mock fixtures. Values are illustrative and mirror docs/specs/api-spec.md examples.
// Version strings live here (the fake backend), never in UI code (UI-01).

import type { SourcesResponse } from '@/types/sources'
import type { SseSource } from '@/types/sse'

export const MOCK_SOURCES: SourcesResponse = {
  sources: [
    {
      sourceKey: 'langchain_v03',
      framework: 'langchain',
      versionLabel: 'v0.3',
      displayName: 'LangChain v0.3',
      enabled: true,
      activeRun: {
        commitSha: 'a4f2e81c3d7b9e0f1a2b3c4d5e6f708192a3b4c5',
        ingestedAt: '2026-10-28',
        chunkCount: 1247,
      },
    },
    {
      sourceKey: 'langchain_v1x',
      framework: 'langchain',
      versionLabel: 'v1.x',
      displayName: 'LangChain v1.x',
      enabled: true,
      activeRun: {
        commitSha: '7c3d9f2a1e5b6c7d8e9f0a1b2c3d4e5f60718293',
        ingestedAt: '2026-10-30',
        chunkCount: 8934,
      },
    },
  ],
  comparePairs: [{ compareEnabled: true, sourceKeyA: 'langchain_v03', sourceKeyB: 'langchain_v1x' }],
  guest: { limit: 5, used: 0, remaining: 5, expiresAt: null },
}

export function findSource(sourceKey: string | null | undefined) {
  return MOCK_SOURCES.sources.find((s) => s.sourceKey === sourceKey) ?? null
}

interface AnswerFixture {
  sources: Omit<SseSource, 'permalink'>[]
  files: string[]
  answer: string
}

const LEGACY: AnswerFixture = {
  files: ['docs/docs/how_to/sequence.ipynb', 'docs/docs/versions/migrating_chains/llm_chain.ipynb'],
  sources: [
    {
      rank: 1,
      headingPath: 'How-to guides > Chains > LLMChain — Getting Started',
      siteUrl: 'https://python.langchain.com/v0.3/docs/how_to/sequence/',
      similarity: 0.88,
    },
    {
      rank: 2,
      headingPath: 'Versions > Migrating chains > SequentialChain API Reference',
      siteUrl: 'https://python.langchain.com/v0.3/docs/versions/migrating_chains/llm_chain/',
      similarity: 0.81,
    },
  ],
  answer: [
    '이 버전 문서 기준으로 체인을 구성하는 방법을 설명드릴게요. [1]',
    '',
    '```python',
    'from langchain.chains import LLMChain',
    'from langchain.prompts import PromptTemplate',
    '',
    'prompt = PromptTemplate(',
    '    input_variables=["question"],',
    '    template="Answer: {question}"',
    ')',
    'chain = LLMChain(llm=llm, prompt=prompt)',
    'result = chain.run(question="Hello")',
    '```',
    '',
    '**run()**은 레거시 체인에서 쓰던 호출 방식이고, 여러 체인을 이어 붙일 때는 `SequentialChain`을 사용합니다. [2]',
    '',
    '- 각 체인의 출력이 다음 체인의 입력으로 전달됩니다. [2]',
    '- 새 코드에서는 `invoke()` 사용이 권장됩니다. [1]',
  ].join('\n'),
}

const MODERN: AnswerFixture = {
  files: [
    'src/oss/python/langchain/runnables.mdx',
    'src/oss/python/migrate/langchain-v1.mdx',
    'src/oss/python/langchain/models.mdx',
  ],
  sources: [
    {
      rank: 1,
      headingPath: 'Core components > Runnables > LCEL Primitives — Invoke',
      siteUrl: 'https://docs.langchain.com/oss/python/langchain/runnables',
      similarity: 0.91,
    },
    {
      rank: 2,
      headingPath: 'Migrate > LangChain v1 > Migration Guide — run() to invoke()',
      siteUrl: 'https://docs.langchain.com/oss/python/migrate/langchain-v1',
      similarity: 0.87,
    },
    {
      rank: 3,
      headingPath: 'Core components > Models > BaseLLM API Reference',
      siteUrl: 'https://docs.langchain.com/oss/python/langchain/models',
      similarity: 0.82,
    },
  ],
  answer: [
    '이 버전 문서 기준으로 `run()`과 `invoke()`의 차이를 설명드릴게요. [1]',
    '',
    '**invoke()**는 Runnable 인터페이스의 표준 메서드로, LCEL 체인 전체에서 일관되게 사용됩니다:',
    '',
    '```python',
    'from langchain_openai import ChatOpenAI',
    'from langchain_core.messages import HumanMessage',
    '',
    'llm = ChatOpenAI()',
    '# invoke()는 Runnable 인터페이스의 표준 메서드',
    'result = llm.invoke([HumanMessage(content="Hello")])',
    'print(result.content)',
    '```',
    '',
    '**run()**은 레거시 메서드로 deprecated 되었습니다. [2] 체인(Chain) 클래스에서만 사용 가능했으며 반환 타입이 일관되지 않았습니다.',
    '',
    '모든 Runnable 객체에 `invoke()`를 사용하세요. [3] 존재하지 않는 근거 번호는 비활성으로 표시됩니다. [7]',
  ].join('\n'),
}

/** Picks a fixture by catalog position so the mock does not branch on version strings. */
export function answerFixture(sourceKey: string): { answer: string; sources: SseSource[] } {
  const index = MOCK_SOURCES.sources.findIndex((s) => s.sourceKey === sourceKey)
  const fixture = index <= 0 ? LEGACY : MODERN
  const source = findSource(sourceKey)
  const sha = source?.activeRun.commitSha ?? '0'.repeat(40)
  const repo = index <= 0 ? 'langchain-ai/langchain' : 'langchain-ai/docs'
  return {
    answer: fixture.answer,
    sources: fixture.sources.map((s, i) => ({
      ...s,
      permalink: `https://github.com/${repo}/blob/${sha}/${fixture.files[i % fixture.files.length]}?plain=1#L${10 + i * 40}-L${42 + i * 40}`,
    })),
  }
}

/** Splits text into small chunks to imitate token streaming. */
export function toTokens(text: string): string[] {
  return text.match(/[\s\S]{1,6}/g) ?? []
}

export function newRequestId(): string {
  return crypto.randomUUID()
}
