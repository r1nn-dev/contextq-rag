# 평가 시나리오

> **최종 수정**: 2026-11-17

---

## 1. 개요

- **목적**: RAG 파이프라인의 검색 품질·버전 정확도·NO_CONTEXT 처리를 평가하기 위해 실험별 질문 시나리오를 정의한다. 각 질문셋은 실험 E1~E3의 입력으로 사용되며, 실험 전 커밋으로 고정하여 사후 수정을 차단한다.
- **질문셋 수**: Q-ret (40개), Q-oos (10개), Q-shared (20개 × 2버전)
- **사용 실험**: E1 (버전 격리 혼입 측정), E2 (청킹 전략 비교), E3 (답변 버전 정확도 비교)
- **정답 라벨 기준**: `eval/decision_rules.md` 커밋 기준 (실험 `eval-v1` 태그 이전에 고정)
- **작성 주체**: AI가 초안을 쓰고 사람이 검수한다(`docs/specs/data-sources.md` §4). 검수를 마친 질문셋만 `eval-v1` 태그로 고정한다.

---

## 2. 공통 규약

### 2.1 질문셋 ID 규칙

| 항목 | 규칙 |
| --- | --- |
| 형식 | `{셋}-{3자리 숫자}` (예: `RET-001`) |
| 셋 접두사 | `RET` (Q-ret), `OOS` (Q-oos), `SHR` (Q-shared) |
| 채번 | 순차 부여. 폐기 시 결번 유지 (재사용 금지) |
| 파일명 | `eval/questions/{셋 접두사}/{ID}.yaml` (예: `eval/questions/RET/RET-001.yaml`). 질문 1개 = 파일 1개 |

### 2.2 버전 표기

| 값 | 의미 |
| --- | --- |
| `v0.3` | LangChain v0.3 (`langchain-ai/langchain` v0.3 브랜치 기준) |
| `v1.x` | LangChain v1.x (`langchain-ai/docs` main 브랜치 기준) |
| `both` | Q-shared: 두 버전 모두 질문 가능 |

### 2.3 정답 판정 기준

| 셋 | 판정 단위 | 판정 방식 |
| --- | --- | --- |
| Q-ret | 청크 단위 — 반환된 Top-K 청크에 정답 섹션이 포함되는지 | Gold 섹션 경로 목록과 대조 (Hit@K, MRR@K) |
| Q-oos | 응답 단위 — NO_CONTEXT 처리 여부 | LLM 미호출 여부 + 안내 메시지 반환 여부 |
| Q-shared | 응답 단위 — 버전 오류 포함 여부 | 블라인드 레이블링 (0 = 오류 없음, 1 = 버전 오류 포함) |

### 2.4 질문 유형 분류

| 유형 코드 | 설명 | 주 사용 셋 |
| --- | --- | --- |
| `VERSION_SPECIFIC` | 특정 버전에서만 유효한 API·클래스·메서드 질문 | Q-ret, Q-shared |
| `API_USAGE` | 특정 클래스·함수의 사용법 질문 | Q-ret |
| `MIGRATION` | v0.3 → v1.x 사이 변경점 질문 | Q-shared |
| `CONCEPT` | 개념 설명 질문 (버전 중립적이거나 버전 차이 있음) | Q-ret, Q-shared |
| `CODE_PATTERN` | 코드 패턴·예제 질문 | Q-ret |
| `OUT_OF_SCOPE` | LangChain 문서 범위 밖 질문 | Q-oos |

### 2.5 난이도 등급

| 등급 | 설명 |
| --- | --- |
| `EASY` | 단일 섹션에서 직접 답변 가능한 질문 |
| `MEDIUM` | 여러 섹션 종합이 필요하거나 버전 간 차이가 있는 질문 |
| `HARD` | 세부 구현 차이·버전 혼입이 쉬운 질문. 비격리 조건에서 혼입 발생 가능성 높음 |

### 2.6 Gold 섹션 기록 규칙

| 항목 | 규칙 |
| --- | --- |
| 단위 | `{file_path, heading_path}` 쌍. `chunk_id`는 청킹 전략마다 달라지므로 쓰지 않는다(정책서 §4.1) |
| `file_path` | 소스 저장소 루트 기준 경로. 청크 메타데이터 `file_path`와 같은 값 (예: `src/oss/langchain/tools.mdx`) |
| `heading_path` | 청크 메타데이터 `heading_path`와 같은 형식(`페이지 제목 > H2`). **깊이는 2 이하** — 전략 C가 H2 단위로 청크를 묶기 때문에 H3 이하를 gold로 쓰면 전략 간 비교가 불공정해진다 |
| 적중 판정 | 청크의 `file_path`가 같고, `heading_path`가 gold와 같거나 gold의 하위 섹션(`gold + " > "`로 시작)이면 적중. 대소문자 무시, 앞뒤 공백 제거 후 비교(`evaluation.md` §2.1) |
| 범위 | 현재 ACTIVE 인덱스에 있는 섹션만 쓴다. 정책서 §3.2 제외 범위(`integrations/**`·`langgraph`)는 gold로 쓰지 않는다 |
| 버전 배분 | Q-ret 40개 = 버전별 20개(디코이 버전별 5개). 디코이도 `target_version`을 지정하고 그 버전 gold만 적는다 |

---

## 3. YAML 스키마

### 3.1 Q-ret / Q-oos 스키마

```yaml
question_id: string        # {셋}-{3자리 숫자}. 필수.
question_set: string       # "Q-ret" | "Q-oos". 필수.
title: string              # 짧은 설명. 필수.
type: string               # 2.4 유형 코드. 필수.
difficulty: string         # EASY | MEDIUM | HARD. 필수.
target_version: string     # Q-ret: v0.3 | v1.x (필수). Q-oos: null

query: string              # 사용자가 입력할 질문 텍스트. 필수.

gold:                      # Q-ret 필수. Q-oos는 쓰지 않음.
  sections:                # 정답 섹션 목록 (2.6 규칙). 1개 이상
    - file_path: string    # 예: "src/oss/langchain/tools.mdx"
      heading_path: string # 예: "Tools > Create tools" (깊이 2 이하)
  note: string             # 정답 판정 보조 설명. 선택.

expected_behavior:         # Q-oos 필수.
  no_context: boolean      # true면 LLM 미호출 + 안내 메시지 반환
  reason: string           # 범위 밖인 이유
  tau_calibration: boolean # τ 결정(E1 부속) 표본 포함 여부. 기본 true. 범위 밖이 아니라 모호해서 걸리는 질문은 false — 동작 확인용으로만 쓴다

metadata:
  created_by: string
  created_at: string       # ISO 8601
  is_decoy: boolean        # Q-ret 디코이 여부 (4장). 기본 false
  reviewed_by: string      # 사람 검수자. 검수 전 null (data-sources.md §4 검수 절차)
  source: string           # 질문 출처/참고 (선택)
```

### 3.2 Q-shared 스키마

```yaml
question_id: string        # SHR-{3자리 숫자}. 필수.
question_set: "Q-shared"
title: string
type: string               # VERSION_SPECIFIC | MIGRATION | CONCEPT
difficulty: string

query: string              # 두 버전 공통으로 사용하는 질문 텍스트

versions:                  # 두 버전에 대한 정보. 컬렉션 이름(run id)은 실행마다 바뀌므로 소스 키만 적는다
  v0_3:
    source_key: "langchain_v03"
    gold_sections:              # v0.3 정답 섹션 (2.6 규칙)
      - file_path: string
        heading_path: string
  v1_x:
    source_key: "langchain_v1x"
    gold_sections:              # v1.x 정답 섹션 (2.6 규칙)
      - file_path: string
        heading_path: string

label_schema:              # E3 블라인드 레이블링 기준
  version_error: "0 = 버전 오류 없음 / 1 = 선택한 버전이 아닌 코드·API 포함"
  evidence_quality: "R1·R2 조건만: 0 = 근거 없음 / 1 = 부분 / 2 = 충분"
  answer_usefulness: "0 = 무관 / 1 = 부분 유용 / 2 = 유용"

metadata:
  created_by: string
  created_at: string
  reviewed_by: string      # 사람 검수자. 검수 전 null
```

### 3.3 YAML 예시 — Q-ret

```yaml
question_id: RET-001
question_set: Q-ret
title: "LangChain v1.x에서 에이전트에 커스텀 툴 추가하기"
type: API_USAGE
difficulty: MEDIUM
target_version: v1.x

query: "LangChain v1.x에서 에이전트에 커스텀 함수 툴을 정의하고 추가하는 방법을 알려줘."

gold:
  sections:
    - file_path: "src/oss/langchain/tools.mdx"
      heading_path: "Tools > Create tools"
  note: "@tool 데코레이터 정의와 create_agent(tools=[...]) 전달"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
  is_decoy: false
  source: "실제 학습자 질문 패턴 참조"
```

### 3.4 YAML 예시 — Q-oos

```yaml
question_id: OOS-001
question_set: Q-oos
title: "Django ORM 사용법 (범위 외)"
type: OUT_OF_SCOPE
difficulty: EASY
target_version: null

query: "Django ORM에서 ForeignKey 관계를 정의하는 방법은?"

expected_behavior:
  no_context: true
  reason: "LangChain 공식 문서에 Django 관련 내용이 없음. 유사도 임계값 τ 미만으로 NO_CONTEXT 반환 예상"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
```

### 3.5 YAML 예시 — Q-shared

```yaml
question_id: SHR-001
question_set: Q-shared
title: "에이전트 생성 방식 (v0.3 vs v1.x)"
type: VERSION_SPECIFIC
difficulty: HARD

query: "LangChain에서 에이전트를 생성하는 방법을 알려줘."

versions:
  v0_3:
    source_key: "langchain_v03"
    gold_sections:
      - file_path: "docs/docs/how_to/agent_executor.ipynb"
        heading_path: "Build an Agent with AgentExecutor (Legacy)"
  v1_x:
    source_key: "langchain_v1x"
    gold_sections:
      - file_path: "src/oss/langchain/agents.mdx"
        heading_path: "Agents > Core components"

label_schema:
  version_error: "0 = 버전 오류 없음 / 1 = 선택한 버전이 아닌 코드·API 포함"
  evidence_quality: "R1·R2 조건만: 0 = 근거 없음 / 1 = 부분 / 2 = 충분"
  answer_usefulness: "0 = 무관 / 1 = 부분 유용 / 2 = 유용"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
```

---

## 4. 디코이 규칙 (Q-ret E2 평가 전용)

> 디코이 = 청킹 전략 평가 시 오검색하기 쉬운 질문. 주제는 LangChain이지만 정답 청크가 명확히 없거나, 버전이 다른 청크가 상위 유사도로 올라올 가능성이 있는 질문.

| 항목 | 규칙 |
| --- | --- |
| 목적 | 청킹 전략 간 Precision@K 측정 — 주제는 맞지만 버전이 틀린 청크 혼입 비율 |
| 비율 | Q-ret 40개 중 10개 (25%) |
| 생성 방법 | 같은 개념·API를 버전을 명시하지 않고 질문하여 양쪽 버전 청크가 경쟁하도록 설계 |
| 표기 | `metadata.is_decoy: true`, gold sections는 target_version에 해당하는 쪽만 |

---

## 5. 질문셋 목록

> 상태: ⬜ 계획 / 📝 초안(AI 작성, 사람 검수 전) / ✅ 검수 완료. 원본은 `eval/questions/` YAML이며 이 표는 목록 요약이다.
> 계획 단계 제목에서 바뀐 문항은 비고에 사유를 적는다(작성 전 변경이라 결번 아님, §2.1).

### 5.1 Q-ret (검색 품질 평가, E1·E2 사용)

| ID | 제목 | 유형 | 난이도 | 버전 | 디코이 | 상태 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RET-001 | v1.x 커스텀 툴 추가 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-002 | v0.3 LLMChain 사용법 | API_USAGE | EASY | v0.3 | N | ✅ |  |
| RET-003 | v1.x 커스텀 미들웨어 훅 | CODE_PATTERN | MEDIUM | v1.x | N | ✅ | 계획 'v1.x LCEL 파이프라인' → v1.x 코퍼스에 LCEL 문서 없음 |
| RET-004 | v0.3 ConversationBufferMemory | API_USAGE | EASY | v0.3 | N | ✅ |  |
| RET-005 | v1.x 메시지로 프롬프트 구성 | API_USAGE | EASY | v1.x | N | ✅ | 계획 'v1.x ChatPromptTemplate' → v1.x 코퍼스에 프롬프트 템플릿 문서 없음 |
| RET-006 | 에이전트 개념 설명 (버전 명시 없음) | CONCEPT | MEDIUM | v0.3 | Y | ✅ |  |
| RET-007 | v1.x 벡터 검색 구성 | CODE_PATTERN | MEDIUM | v1.x | N | ✅ | 계획 'RAG 체인' → v1.x 코퍼스 RAG 기초는 semantic search 튜토리얼 |
| RET-008 | v0.3 PromptTemplate 형식 | API_USAGE | EASY | v0.3 | N | ✅ |  |
| RET-009 | v1.x 스트리밍 응답 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-010 | Retriever 개념 (버전 명시 없음) | CONCEPT | EASY | v0.3 | Y | ✅ |  |
| RET-011 | v0.3 LCEL 파이프 연산자 체인 | CODE_PATTERN | MEDIUM | v0.3 | N | ✅ |  |
| RET-012 | v0.3 RunnableParallel | API_USAGE | MEDIUM | v0.3 | N | ✅ |  |
| RET-013 | v0.3 AgentExecutor 실행 | VERSION_SPECIFIC | HARD | v0.3 | N | ✅ |  |
| RET-014 | v0.3 RunnableWithMessageHistory | API_USAGE | MEDIUM | v0.3 | N | ✅ |  |
| RET-015 | v0.3 with_structured_output | API_USAGE | MEDIUM | v0.3 | N | ✅ |  |
| RET-016 | v0.3 bind_tools 도구 호출 | API_USAGE | MEDIUM | v0.3 | N | ✅ |  |
| RET-017 | v0.3 커스텀 콜백 핸들러 | CODE_PATTERN | MEDIUM | v0.3 | N | ✅ |  |
| RET-018 | v0.3 RecursiveCharacterTextSplitter | API_USAGE | EASY | v0.3 | N | ✅ |  |
| RET-019 | v0.3 Runnable 폴백 | API_USAGE | MEDIUM | v0.3 | N | ✅ |  |
| RET-020 | v0.3 astream_events | API_USAGE | HARD | v0.3 | N | ✅ |  |
| RET-021 | v0.3 RetrievalQA 마이그레이션 | VERSION_SPECIFIC | MEDIUM | v0.3 | N | ✅ |  |
| RET-022 | 출력 파싱 (버전 명시 없음) | CONCEPT | MEDIUM | v0.3 | Y | ✅ |  |
| RET-023 | 채팅 모델 스트리밍 (버전 명시 없음) | API_USAGE | MEDIUM | v0.3 | Y | ✅ |  |
| RET-024 | 도구 정의 (버전 명시 없음) | API_USAGE | EASY | v0.3 | Y | ✅ |  |
| RET-025 | v0.3 채팅 모델 응답 캐시 | API_USAGE | EASY | v0.3 | N | ✅ |  |
| RET-026 | v1.x create_agent 에이전트 생성 | API_USAGE | EASY | v1.x | N | ✅ |  |
| RET-027 | v1.x 에이전트 구조화 출력 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-028 | v1.x 도구 실행 전 사람 승인 | API_USAGE | HARD | v1.x | N | ✅ |  |
| RET-029 | v1.x 운영 환경 단기 메모리 저장소 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-030 | v1.x 메시지 자르기·요약 | CODE_PATTERN | MEDIUM | v1.x | N | ✅ |  |
| RET-031 | v1.x init_chat_model | API_USAGE | EASY | v1.x | N | ✅ |  |
| RET-032 | v1.x MCP 도구 연결 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-033 | v1.x 도구에서 런타임 컨텍스트 접근 | API_USAGE | HARD | v1.x | N | ✅ |  |
| RET-034 | v1.x 기본 제공 미들웨어 | API_USAGE | MEDIUM | v1.x | N | ✅ |  |
| RET-035 | v1.x 레거시 코드 이동 (langchain-classic) | VERSION_SPECIFIC | MEDIUM | v1.x | N | ✅ |  |
| RET-036 | 대화 기억 추가 (버전 명시 없음) | CONCEPT | MEDIUM | v1.x | Y | ✅ |  |
| RET-037 | 모델 도구 호출 (버전 명시 없음) | API_USAGE | MEDIUM | v1.x | Y | ✅ |  |
| RET-038 | 멀티모달 입력 (버전 명시 없음) | API_USAGE | MEDIUM | v1.x | Y | ✅ |  |
| RET-039 | 도구 실행 오류 처리 (버전 명시 없음) | API_USAGE | MEDIUM | v1.x | Y | ✅ |  |
| RET-040 | 메시지 타입 구분 (버전 명시 없음) | CONCEPT | EASY | v1.x | Y | ✅ |  |

### 5.2 Q-oos (NO_CONTEXT 처리 검증, E1 부속)

| ID | 제목 | 유형 | 난이도 | 상태 |
| --- | --- | --- | --- | --- |
| OOS-001 | Django ORM ForeignKey (범위 외) | OUT_OF_SCOPE | EASY | ✅ |
| OOS-002 | FastAPI 의존성 주입 (범위 외) | OUT_OF_SCOPE | EASY | ✅ |
| OOS-003 | PyTorch 텐서 연산 (범위 외) | OUT_OF_SCOPE | EASY | ✅ |
| OOS-004 | NumPy 배열 슬라이싱 (범위 외) | OUT_OF_SCOPE | EASY | ✅ |
| OOS-005 | React 컴포넌트 생성 (범위 외) | OUT_OF_SCOPE | EASY | ✅ |
| OOS-006 | Kubernetes Helm 배포 (범위 외 운영) | OUT_OF_SCOPE | MEDIUM | ✅ |
| OOS-007 | LangGraph Functional API (범위 외 패키지) | OUT_OF_SCOPE | MEDIUM | ✅ |
| OOS-008 | 의도적으로 모호한 질문 (τ 결정 표본 제외) | OUT_OF_SCOPE | HARD | ✅ |
| OOS-009 | 다음 메이저 버전 출시일 (미래 정보) | OUT_OF_SCOPE | MEDIUM | ✅ |
| OOS-010 | 한국어 LangChain 문서 (언어 범위 외) | OUT_OF_SCOPE | EASY | ✅ |

### 5.3 Q-shared (버전 정확도 비교, E3 사용)

| ID | 제목 | 유형 | 난이도 | 혼입 위험 | 상태 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| SHR-001 | 에이전트 생성 방식 | VERSION_SPECIFIC | HARD | 높음 | ✅ |  |
| SHR-002 | 체인 구성 방식 | MIGRATION | HARD | 높음 | ✅ |  |
| SHR-003 | Retriever 연결 방식 | VERSION_SPECIFIC | MEDIUM | 중간 | ✅ |  |
| SHR-004 | 메모리 관리 방식 | VERSION_SPECIFIC | MEDIUM | 높음 | ✅ |  |
| SHR-005 | 프롬프트 템플릿 사용 | API_USAGE | EASY | 낮음 | ✅ |  |
| SHR-006 | 도구 실행 전 사람 승인 | VERSION_SPECIFIC | MEDIUM | 중간 | ✅ | 계획 '콜백 핸들러 등록' → v1.x 코퍼스에 콜백 문서 없음 |
| SHR-007 | 모델 호출 전후 사용자 정의 로직 | VERSION_SPECIFIC | MEDIUM | 높음 | ✅ | 검수 교체(#103): 이전 '채팅 모델 초기화'는 두 버전 답이 같음 → 콜백 핸들러 / 미들웨어 훅 |
| SHR-008 | 도구 실행 오류 처리 | VERSION_SPECIFIC | MEDIUM | 높음 | ✅ | 검수 교체(#103): 이전 '문서 로더 사용법'은 두 버전 답이 같음 → `ToolException` / `@wrap_tool_call` |
| SHR-009 | 긴 대화 메시지 줄이기 | VERSION_SPECIFIC | MEDIUM | 중간 | ✅ | 검수 교체(#103): 이전 '텍스트 분할기'는 두 버전 답이 같음 → `trim_messages` / 단기 메모리 패턴 |
| SHR-010 | 실행 중 모델 바꾸기 | VERSION_SPECIFIC | HARD | 높음 | ✅ | 검수 교체(#103): 이전 '임베딩 모델 연결'은 두 버전 답이 같음 → `configurable_alternatives` / 동적 모델 선택 |
| SHR-011 | 벡터스토어 저장/검색 | API_USAGE | MEDIUM | 중간 | ✅ |  |
| SHR-012 | 스트리밍 출력 | VERSION_SPECIFIC | MEDIUM | 높음 | ✅ |  |
| SHR-013 | 모델 호출 폴백·재시도 | VERSION_SPECIFIC | HARD | 중간 | ✅ | 계획 '비동기 호출 방식' → v1.x 코퍼스에 비동기 전용 섹션 없음 |
| SHR-014 | 메시지 타입 구분 | API_USAGE | EASY | 낮음 | ✅ | 계획 '출력 파서 사용' → v1.x 코퍼스에 출력 파서 문서 없음(SHR-017과 중복 회피) |
| SHR-015 | 버전 업그레이드 | MIGRATION | MEDIUM | 높음 | ✅ | 계획 'LCEL vs 체인 비교' → SHR-002와 중복 |
| SHR-016 | 도구 정의 방식 | VERSION_SPECIFIC | MEDIUM | 중간 | ✅ |  |
| SHR-017 | JSON 출력 강제 | API_USAGE | MEDIUM | 중간 | ✅ |  |
| SHR-018 | 로컬 모델 연결 | API_USAGE | MEDIUM | 낮음 | ✅ | 계획 '허깅페이스 모델 연결' → `integrations/**` 제외 범위(정책서 §3.2) |
| SHR-019 | 패키지 설치 방법 | CONCEPT | EASY | 낮음 | ✅ |  |
| SHR-020 | 디버그·추적 방법 | VERSION_SPECIFIC | MEDIUM | 중간 | ✅ |  |

---

## 6. 시나리오 상세 신규 추가 템플릿

```
### {ID}: {제목}

| 항목 | 값 |
| --- | --- |
| **ID** | `{셋}-{번호}` |
| **유형** | `{2.4 유형 코드}` |
| **난이도** | EASY / MEDIUM / HARD |
| **버전** | v0.3 / v1.x / both / null |
| **상태** | 설계 / 완료 |

**질문**: {사용자가 입력할 텍스트}

**Gold 섹션** (Q-ret만):
- `{heading_path 1}`
- `{heading_path 2}`

**판정 기준**:
- {예: v0.3 AgentExecutor를 사용하는 코드가 포함된 경우 버전 오류}
- {경계 케이스: ...}

#### YAML
{3.1 또는 3.2 스키마를 따른 YAML 블록}
```

---

## 7. 시나리오 상세

> 셋별 대표 예시 1개씩만 판정 기준을 풀어 쓴다. 전체 문항의 원본은 `eval/questions/` YAML이다(YAML 예시는 §3.3~§3.5).

### RET-001: v1.x 커스텀 툴 추가

| 항목 | 값 |
| --- | --- |
| **ID** | `RET-001` |
| **유형** | `API_USAGE` |
| **난이도** | MEDIUM |
| **버전** | v1.x |
| **상태** | 📝 초안 |

**질문**: "LangChain v1.x에서 에이전트에 커스텀 함수 툴을 정의하고 추가하는 방법을 알려줘."

**Gold 섹션**:
- `src/oss/langchain/tools.mdx` · `Tools > Create tools`

**판정 기준**:
- Hit@K: `tools.mdx`의 `Tools > Create tools` 또는 그 하위 섹션 청크가 Top-K에 있으면 HIT (§2.6)
- 경계 케이스: v0.3의 `Tool(name=..., func=...)` 패턴이 포함된 청크가 반환되면 버전 혼입으로 E1 측정

파일: `eval/questions/RET/RET-001.yaml`

---

### OOS-001: Django ORM ForeignKey (범위 외)

| 항목 | 값 |
| --- | --- |
| **ID** | `OOS-001` |
| **유형** | `OUT_OF_SCOPE` |
| **난이도** | EASY |
| **버전** | null |
| **상태** | 📝 초안 |

**질문**: "Django ORM에서 ForeignKey 관계를 정의하는 방법은?"

**판정 기준**:
- NO_CONTEXT: 반환 `max_score < τ` → LLM 미호출, 안내 메시지 반환
- 합격: "선택한 버전 문서에서 근거를 찾을 수 없습니다" 메시지 반환
- 실패: LLM이 호출되어 Django 내용을 답변하거나, 무관한 LangChain 내용으로 답변

파일: `eval/questions/OOS/OOS-001.yaml`

---

### SHR-001: 에이전트 생성 방식 (v0.3 vs v1.x)

| 항목 | 값 |
| --- | --- |
| **ID** | `SHR-001` |
| **유형** | `VERSION_SPECIFIC` |
| **난이도** | HARD |
| **버전** | both |
| **상태** | 📝 초안 |

**질문**: "LangChain에서 에이전트를 생성하는 방법을 알려줘."

**Gold 섹션**:
- v0.3: `docs/docs/how_to/agent_executor.ipynb` · `Build an Agent with AgentExecutor (Legacy)`, `docs/docs/tutorials/agents.ipynb` · `Build an Agent`
- v1.x: `src/oss/langchain/agents.mdx` · `Agents > Core components`, `src/oss/langchain/overview.mdx` · `LangChain overview > Create an agent`
- 계획 단계의 v1.x gold `LangGraph > Agent > Concepts`는 `langgraph` 제외 범위(정책서 §3.2)라 교체했다.

**판정 기준** (E3 블라인드 레이블링, `eval/rubric.md`):
- 버전 오류 (1): 선택 버전이 v0.3인데 `create_agent()` (v1.x API)가 답변에 포함된 경우, 또는 v1.x인데 `AgentExecutor(agent=..., tools=...)` (v0.3 패턴)이 포함된 경우
- 정상 (0): 선택 버전의 API만 사용하여 답변
- 경계 케이스: 개념 설명만 하고 코드 없는 경우 → 버전 혼입 없으면 0

파일: `eval/questions/SHR/SHR-001.yaml`

---

## 미결정 사항

- [x] RET-011~040 질문 목록 초안 작성 (2026-11-17, AI 초안 — 사람 검수 대기)
- [x] 70문항 검수(`metadata.reviewed_by`) — AI 사전 검토 + 사람 최종 판단, 기록 `eval/review_v1.md` (#103)
- [ ] `eval/decision_rules.md` §6 확정 후 `eval-v1` 태그
- [x] NO_CONTEXT 임계값 τ 결정 (E1 부속, 2026-11-18) — v0.3 0.29 · v1.x 0.34 (`eval/results/E1/analysis.md`)
- [x] Q-shared SHR-002~020 gold 섹션 초안 (2026-11-17, ACTIVE 인덱스 v0.3 run 1 · v1.x run 3과 대조 누락 0건)
- [ ] E3 블라인드 레이블링 루브릭 외부 리뷰어와 사전 조율 (W4 이전)

---

*end.*
