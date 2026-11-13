# 문서 수집 및 전처리 명세

> **최종 수정**: 2026-11-05

---

## 1. 개요

- **목적**: v0.3 Docusaurus `.md/.mdx`와 v1.x Mintlify `.mdx` 두 포맷을 단일 `NormalizedDocument` TypedDict로 통일하는 Source Adapter의 설계 근거와 구현 규칙을 명시한다.
- **범위**: 파싱 규칙, 필드 도출 알고리즘, 신규 소스 추가 절차를 포함한다. 전처리 스크립트 실행 절차는 `claude/data-sources.md`를, Chroma 적재 이후 파이프라인은 `claude/rag-pipeline.md`를 참조한다.
- **설계 원칙**: ai-server 내부의 검색·생성 로직은 소스 포맷을 몰라야 한다. Source Adapter가 포맷 차이를 흡수하고 `NormalizedDocument`를 반환하면, 그 위의 모든 계층은 단일 인터페이스만 사용한다.

---

## 2. NormalizedDocument 스키마

`ai_server/domain/models.py`에 정의한다.

```python
from typing import TypedDict

class NormalizedDocument(TypedDict):
    chunk_id:     str    # "{file_stem}_{seq:04d}"  예) "agents_tools_0012"
    source_key:   str    # "langchain_v03" | "langchain_v1x"  (Chroma 컬렉션 접두사와 일치)
    source_file:  str    # 버전 루트 기준 상대 경로  예) "how_to/agent.mdx"
    heading_path: str    # "H1 > H2 > H3" 직렬화  예) "Agents > Tool Calling > Basics"
    permalink:    str    # GitHub SHA-fixed URL + #anchor
    text:         str    # 전처리 완료된 청크 텍스트
    token_count:  int    # tiktoken cl100k_base 기준 토큰 수
```

> **인터페이스 연관**: `claude/interfaces.md`의 `Retriever.retrieve()` 반환 타입인 `RetrievedChunk`는 `NormalizedDocument`를 상속하며 `similarity: float` 필드를 추가한다.

---

## 3. Source Adapter 패턴

```
SourceAdapter (Protocol)
 ├── DocusaurusAdapter   # v0.3 langchain-ai/langchain docs/docs/
 └── MintlifyAdapter     # v1.x langchain-ai/docs src/oss/
```

```python
from typing import Protocol, Iterator

class SourceAdapter(Protocol):
    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        """root 디렉터리 하위의 모든 파일을 파싱하여 NormalizedDocument를 순회한다."""
        ...
```

호출 측은 `SourceAdapter` 타입만 사용한다. 어떤 Adapter 구현체인지 알지 못한다.

```python
# scripts/data/build_index.py (예시)
adapter: SourceAdapter = DocusaurusAdapter(sha=SHA_V03)
for doc in adapter.iter_documents(root=Path("data/raw/langchain_v03/docs/docs")):
    index_to_chroma(doc)
```

---

## 4. 파싱 공통 규칙

두 Adapter 모두 아래 순서로 파일을 처리한다.

| 단계 | 설명 |
| --- | --- |
| 1. 파일 탐색 | `root` 하위 `.md` / `.mdx` 재귀 탐색. `_`, `.` 로 시작하는 디렉터리 제외 |
| 2. Frontmatter 제거 | 파일 선두 `---\n…\n---` 블록 제거. frontmatter 필드 중 `title`은 heading_path 최상위 보정에 사용 |
| 3. 코드 블록 보호 | ` ``` … ``` ` 범위를 마크로 치환하고 이후 단계에서 내부를 건드리지 않는다. 처리 완료 후 복원 |
| 4. 포맷별 정리 | §5 (Docusaurus) 또는 §6 (Mintlify) 절차 적용 |
| 5. 헤딩 트리 추출 | §7 절차 적용 → heading_path 도출 |
| 6. 청크 분할 | §8 절차 적용 |
| 7. 필드 조립 | §9 규칙에 따라 `chunk_id`, `permalink`, `anchor` 생성 |
| 8. 토큰 계산 | `tiktoken.get_encoding("cl100k_base").encode(text)` 길이 |

---

## 5. Docusaurus Adapter (v0.3)

**대상 경로**: `data/raw/langchain_v03/docs/docs/`
**파일 형식**: `.md`, `.mdx` 혼용

### 5.1 Docusaurus 고유 태그 제거

| 패턴 | 처리 | 비고 |
| --- | --- | --- |
| `:::tip`, `:::note`, `:::warning`, `:::danger`, `:::info` | 블록 경계 태그만 제거, 내부 텍스트 보존 | `:::tip[제목]` 형태도 동일 |
| `import … from '…'` | 행 전체 삭제 | MDX import 선언 |
| `<CodeBlock>…</CodeBlock>` | 태그 제거, 내부 코드 텍스트 보존 | `language` attr 무시 |
| `<Tabs>`, `<TabItem>`, `</Tabs>`, `</TabItem>` | 태그 제거, 내부 텍스트 보존 | |
| 그 외 JSX 인라인 태그 `<[A-Z]\w*[^>]*/>` | 태그 전체 삭제 | 코드 블록 내부 제외 |
| `{/* … */}` JSX 주석 | 삭제 | |

### 5.2 permalink 패턴

```
https://github.com/langchain-ai/langchain/blob/{SHA_V03}/docs/docs/{source_file}#{anchor}
```

- `source_file`: `docs/docs/` 기준 상대 경로 (예: `how_to/agent.mdx`)
- `anchor`: §9.2 앵커 생성 규칙 적용

---

## 6. Mintlify Adapter (v1.x)

**대상 경로**: `data/raw/langchain_v1x/src/oss/`
**스니펫 경로**: `data/raw/langchain_v1x/src/snippets/`
**파일 형식**: `.mdx` (JSX 컴포넌트 사용)

### 6.1 Snippet Expansion

> Mintlify는 반복 코드 블록을 `<ComponentName />` JSX 태그로 삽입한다. 전처리 단계에서 실제 텍스트로 치환해야 검색 품질이 보장된다.

**처리 순서:**

1. 코드 블록 보호(§4 단계 3) 이후, `<[A-Z][A-Za-z]+\s*/>` 패턴을 탐색한다.
2. 컴포넌트 이름 → `src/snippets/` 하위 파일명을 소문자로 정규화하여 매핑한다.

   ```python
   # 예: <LangSmithSetup /> → src/snippets/lang_smith_setup.mdx (대소문자 무시 + snake_case 변환)
   def resolve_snippet(name: str, snippets_dir: Path) -> Path | None:
       candidates = list(snippets_dir.glob("*.mdx"))
       lower_name = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', name).lower()  # CamelCase → snake_case
       for c in candidates:
           if c.stem.lower() == lower_name:
               return c
       return None
   ```

3. 매핑 성공 시 태그를 스니펫 본문으로 치환한다. 스니펫 자체에도 frontmatter가 있으면 제거한다.
4. 매핑 실패 시 태그를 삭제하고 경고를 `logs/preprocess_v1x_warnings.txt`에 기록한다:
   ```
   WARN [snippet_not_found] <LangGraphSetup /> in src/oss/how-to/agent.mdx
   ```

### 6.2 Mintlify 고유 태그 제거

| 패턴 | 처리 |
| --- | --- |
| `<Callout type="…">…</Callout>` | 태그 제거, 내부 텍스트 보존 |
| `<Card>`, `<CardGroup>`, `</Card>`, `</CardGroup>` | 태그 제거, 내부 텍스트 보존 |
| `<Steps>`, `<Step title="…">`, `</Steps>`, `</Step>` | 태그 제거, `title` 속성 값은 텍스트로 삽입 |
| `<Accordion title="…">…</Accordion>` | 태그 제거, `title` 속성 값은 텍스트로 삽입 |
| `<Tabs>`, `<Tab title="…">`, `</Tabs>`, `</Tab>` | 태그 제거, `title` 속성 값은 텍스트로 삽입 |
| `export const … = …` | 행 전체 삭제 |
| JSX 주석 `{/* … */}` | 삭제 |
| 나머지 Uppercase JSX 태그 | 태그 제거, 내부 텍스트 보존 |

### 6.3 permalink 패턴

```
https://github.com/langchain-ai/docs/blob/{SHA_V1X}/src/oss/{source_file}#{anchor}
```

- `source_file`: `src/oss/` 기준 상대 경로

---

## 7. 헤딩 트리 추출

### 7.1 헤딩 감지

```python
HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)', re.MULTILINE)
```

- 코드 블록 내부(§4 단계 3의 마크 범위)는 헤딩으로 처리하지 않는다.
- frontmatter의 `title` 필드가 있고 문서 최상위 H1이 없으면 `title`을 H1으로 간주한다.

### 7.2 heading_path 직렬화

```
heading_path = " > ".join([h1_text, h2_text, h3_text])  # 해당 레벨까지만 포함
```

**예시:**

```
# Agents                       → "Agents"
## Tool Calling                → "Agents > Tool Calling"
### Using Custom Tools         → "Agents > Tool Calling > Using Custom Tools"
```

**규칙:**

| 규칙 | 내용 |
| --- | --- |
| 레벨 스킵 | H1 → H3 처럼 H2가 없으면 "Agents > Using Custom Tools" (H2 생략) |
| 헤딩 텍스트 정제 | 텍스트 양쪽 공백 제거, 마크다운 인라인 (`**`, `_`, `` ` ``) 제거 |
| H4 이상 | heading_path에 포함하지 않음. 청크 소속만 H3 단위로 추적 |
| 최상위 헤딩 없음 | 파일 stem을 Title Case로 변환하여 H1로 대체 |

---

## 8. 청크 분할

### 8.1 분할 단위

기본 분할 단위는 **H2 섹션**이다. H2가 없으면 H3을 단위로 한다.

```
Agents (H1)
  ├── [chunk A] Tool Calling (H2) : 220 tokens
  ├── [chunk B] Memory (H2) : 480 tokens
  │     ├── Basics (H3) — chunk B에 포함
  │     └── Advanced (H3) — 480 > 300이면 H3 경계로 추가 분할
  └── [chunk C] Streaming (H2) : 95 tokens → min 미달이면 다음 H2와 병합
```

### 8.2 토큰 범위

| 파라미터 | 기본값 | 설명 |
| --- | --- | --- |
| `MIN_TOKENS` | 100 | 이 미만이면 다음 섹션과 병합 |
| `MAX_TOKENS` | 512 | 초과 시 단락(`\n\n`) 경계에서 추가 분할 |
| `OVERLAP_TOKENS` | 0 | 현재 오버랩 없음 (E2 전략 B·C에서 변경 가능) |

> E2 청킹 전략 A(현행) / B(오버랩 50) / C(MAX_TOKENS=256) 비교 실험은 `claude/protocol.md` §E2 참조.

### 8.3 연속 분할 시 heading_path 처리

단일 H2 섹션이 MAX_TOKENS 초과로 추가 분할될 경우, 모든 분할 청크는 동일한 `heading_path`를 갖는다. `chunk_id`의 `seq`로 순서를 구분한다.

---

## 9. 필드 도출 규칙

### 9.1 chunk_id

```python
chunk_id = f"{file_stem}_{seq:04d}"
# 예: "agents_tool_calling_0003"
```

- `file_stem`: 파일명에서 확장자 제거 후 소문자, 비 alphanumeric을 `_`로 치환
- `seq`: 같은 파일 내 청크 순서 (0부터 시작)
- 같은 sha commit에서 같은 파일이라면 seq가 결정론적으로 재현되어야 한다.

### 9.2 anchor 생성 (GitHub Markdown 헤딩 앵커 규칙)

```python
def to_anchor(heading_text: str) -> str:
    text = heading_text.lower()
    text = re.sub(r'[^\w\s-]', '', text)   # 특수문자 제거 (단, - 보존)
    text = re.sub(r'\s+', '-', text.strip())  # 공백 → -
    return text
```

**예시:**

| 헤딩 텍스트 | anchor |
| --- | --- |
| `Tool Calling` | `tool-calling` |
| `Using `create_react_agent`` | `using-create_react_agent` |
| `What's New in v1.x?` | `whats-new-in-v1x` |

### 9.3 source_file 기준

| 버전 | 버전 루트 | source_file 예 |
| --- | --- | --- |
| v0.3 | `data/raw/langchain_v03/docs/docs/` | `how_to/agent.mdx` |
| v1.x | `data/raw/langchain_v1x/src/oss/` | `how-to/agents/agent-tutorial.mdx` |

---

## 10. 신규 소스 추가 절차

새로운 공식 문서 저장소(예: LangGraph 공식 문서)를 추가할 때 아래 단계를 따른다.

1. `claude/data-sources.md`에 소스 항목을 추가한다 (저장소, 브랜치, 경로, 라이선스).
2. `SourceAdapter` 프로토콜을 구현하는 새 Adapter 클래스를 작성한다:
   - `iter_documents(root: Path) → Iterator[NormalizedDocument]`
   - `source_key` 필드 값을 새로 정의한다 (예: `"langgraph_v01"`).
3. 새 버전에 대한 Chroma 컬렉션 명명 규칙을 `claude/rag-pipeline.md` §3에 추가한다.
4. sparse checkout 스크립트를 `scripts/data/checkout_{source}.sh`로 작성한다.
5. 전처리 스크립트를 `scripts/data/preprocess_{source}.py`로 작성한다.
6. `eval/questions/` 에 새 버전 Q-ret / Q-oos 질문셋을 추가한다.
7. `claude/data-sources.md` §5 라이선스 표를 갱신한다.

> **단일 버전 추가 최소 작업량**: Adapter 1개 + checkout 스크립트 1개 + 전처리 스크립트 1개 + 질문셋 2개 (Q-ret, Q-oos).

---

## 미결 사항

- [ ] **DS-1** Mintlify snippet → snake_case 변환 함수의 엣지케이스 확인 (예: `LLMChain`, `OpenAI` 같은 All-caps 세그먼트 처리)
- [ ] **DS-2** `<Steps>` / `<Step title="…">` title 속성 추출 정규식 검증 — Mintlify 실제 파일로 테스트 필요
- [ ] **DS-3** H2 없는 파일(예: 단일 H3만 존재)의 청크 분할 동작 확인 및 테스트 케이스 추가
- [ ] **DS-4** heading_path의 비 ASCII 문자(한국어 혼재 여부) 처리 규칙 최종 확정 — `data-sources.md` D-5와 연동
- [ ] **DS-5** `MIN_TOKENS` / `MAX_TOKENS` 기본값이 E2 실험 전략 A의 채택값과 일치하는지 E2 완료 후 재확인

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | `NormalizedDocument.version` → `source_key` (통일된 소스 식별자); `RetrievedChunk.score` → `similarity` (API 계약 일치) |

---

*end.*
