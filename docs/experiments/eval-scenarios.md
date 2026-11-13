# 평가 시나리오

> **최종 수정**: 2026-11-04

---

## 1. 개요

- **목적**: RAG 파이프라인의 검색 품질·버전 정확도·NO_CONTEXT 처리를 평가하기 위해 실험별 질문 시나리오를 정의한다. 각 질문셋은 실험 E1~E3의 입력으로 사용되며, 실험 전 커밋으로 고정하여 사후 수정을 차단한다.
- **질문셋 수**: Q-ret (40개), Q-oos (10개), Q-shared (20개 × 2버전)
- **사용 실험**: E1 (버전 격리 혼입 측정), E2 (청킹 전략 비교), E3 (답변 버전 정확도 비교)
- **정답 라벨 기준**: `eval/decision_rules.md` 커밋 기준 (실험 `eval-v1` 태그 이전에 고정)

---

## 2. 공통 규약

### 2.1 질문셋 ID 규칙

| 항목 | 규칙 |
| --- | --- |
| 형식 | `{셋}-{3자리 숫자}` (예: `RET-001`) |
| 셋 접두사 | `RET` (Q-ret), `OOS` (Q-oos), `SHR` (Q-shared) |
| 채번 | 순차 부여. 폐기 시 결번 유지 (재사용 금지) |
| 파일명 | `eval/questions/{셋}/{ID}.yaml` |

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

---

## 3. YAML 스키마

### 3.1 Q-ret / Q-oos 스키마

```yaml
question_id: string        # {셋}-{3자리 숫자}. 필수.
question_set: string       # "Q-ret" | "Q-oos". 필수.
title: string              # 짧은 설명. 필수.
type: string               # 2.4 유형 코드. 필수.
difficulty: string         # EASY | MEDIUM | HARD. 필수.
target_version: string     # v0.3 | v1.x | null (Q-oos는 null 허용)

query: string              # 사용자가 입력할 질문 텍스트. 필수.

gold:                      # Q-ret 필수. Q-oos는 비워둠.
  sections:                # 정답 섹션 경로 목록 (heading_path 형식)
    - string               # 예: "Agents > Tools > Defining tools"
  note: string             # 정답 판정 보조 설명. 선택.

expected_behavior:         # Q-oos 필수.
  no_context: boolean      # true면 LLM 미호출 + 안내 메시지 반환
  reason: string           # 범위 밖인 이유

metadata:
  created_by: string
  created_at: string       # ISO 8601
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

versions:                  # 두 버전에 대한 정보
  v0_3:
    target_collection: string   # langchain_v03_run{id}
    gold_sections: list[string] # v0.3 정답 섹션 경로
  v1_x:
    target_collection: string   # langchain_v1x_run{id}
    gold_sections: list[string] # v1.x 정답 섹션 경로

label_schema:              # E3 블라인드 레이블링 기준
  version_error: "0 = 버전 오류 없음 / 1 = 선택한 버전이 아닌 코드·API 포함"
  evidence_quality: "R1·R2 조건만: 0 = 근거 없음 / 1 = 부분 / 2 = 충분"
  answer_usefulness: "0 = 무관 / 1 = 부분 유용 / 2 = 유용"

metadata:
  created_by: string
  created_at: string
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
    - "Agents > Tools > Defining tools"
    - "Agents > Tools > Toolkits"
  note: "@tool 데코레이터와 StructuredTool.from_function 두 경로 모두 허용"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
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
    target_collection: "langchain_v03_run{id}"
    gold_sections:
      - "Agents > AgentExecutor"
      - "Agents > create_react_agent"
  v1_x:
    target_collection: "langchain_v1x_run{id}"
    gold_sections:
      - "Agents > create_agent"
      - "LangGraph > Agent > Concepts"

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

### 5.1 Q-ret (검색 품질 평가, E1·E2 사용)

| ID | 제목 | 유형 | 난이도 | 버전 | 디코이 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| RET-001 | v1.x 커스텀 툴 추가 | API_USAGE | MEDIUM | v1.x | N | ⬜ |
| RET-002 | v0.3 LLMChain 사용법 | API_USAGE | EASY | v0.3 | N | ⬜ |
| RET-003 | v1.x LCEL 파이프라인 구성 | CODE_PATTERN | MEDIUM | v1.x | N | ⬜ |
| RET-004 | v0.3 ConversationBufferMemory | API_USAGE | EASY | v0.3 | N | ⬜ |
| RET-005 | v1.x ChatPromptTemplate | API_USAGE | EASY | v1.x | N | ⬜ |
| RET-006 | 에이전트 개념 설명 (버전 명시 없음) | CONCEPT | MEDIUM | — | Y | ⬜ |
| RET-007 | v1.x RAG 체인 구성 | CODE_PATTERN | MEDIUM | v1.x | N | ⬜ |
| RET-008 | v0.3 PromptTemplate 형식 | API_USAGE | EASY | v0.3 | N | ⬜ |
| RET-009 | v1.x 스트리밍 응답 | API_USAGE | MEDIUM | v1.x | N | ⬜ |
| RET-010 | Retriever 개념 (버전 명시 없음) | CONCEPT | EASY | — | Y | ⬜ |
| RET-011~040 | (추가 질문) | — | — | — | — | ⬜ |

> 나머지 RET-011~040은 금 레이블링 작업(`W2`)에서 채운다.

### 5.2 Q-oos (NO_CONTEXT 처리 검증, E1 부속)

| ID | 제목 | 유형 | 난이도 | 상태 |
| --- | --- | --- | --- | --- |
| OOS-001 | Django ORM ForeignKey | OUT_OF_SCOPE | EASY | ⬜ |
| OOS-002 | FastAPI 의존성 주입 | OUT_OF_SCOPE | EASY | ⬜ |
| OOS-003 | PyTorch 텐서 연산 | OUT_OF_SCOPE | EASY | ⬜ |
| OOS-004 | NumPy 배열 슬라이싱 | OUT_OF_SCOPE | EASY | ⬜ |
| OOS-005 | React 컴포넌트 생성 | OUT_OF_SCOPE | EASY | ⬜ |
| OOS-006 | LangChain 1.5 버전 기능 (미수집 버전) | OUT_OF_SCOPE | MEDIUM | ⬜ |
| OOS-007 | LangGraph 사용법 (범위 외 패키지) | OUT_OF_SCOPE | MEDIUM | ⬜ |
| OOS-008 | LangChain 개념 질문 (매우 추상적, 의도적 모호) | OUT_OF_SCOPE | HARD | ⬜ |
| OOS-009 | "LangChain 최신 버전이 뭐야?" (실시간 정보) | OUT_OF_SCOPE | MEDIUM | ⬜ |
| OOS-010 | 한국어 LangChain 문서는? (언어 범위 외) | OUT_OF_SCOPE | EASY | ⬜ |

### 5.3 Q-shared (버전 정확도 비교, E3 사용)

| ID | 제목 | 유형 | 난이도 | 혼입 위험 | 상태 |
| --- | --- | --- | --- | --- | --- |
| SHR-001 | 에이전트 생성 방식 | VERSION_SPECIFIC | HARD | 높음 | ⬜ |
| SHR-002 | 체인 구성 방식 | MIGRATION | HARD | 높음 | ⬜ |
| SHR-003 | Retriever 연결 방식 | VERSION_SPECIFIC | MEDIUM | 중간 | ⬜ |
| SHR-004 | 메모리 관리 방식 | VERSION_SPECIFIC | MEDIUM | 높음 | ⬜ |
| SHR-005 | 프롬프트 템플릿 사용 | API_USAGE | EASY | 낮음 | ⬜ |
| SHR-006 | 콜백 핸들러 등록 | API_USAGE | MEDIUM | 중간 | ⬜ |
| SHR-007 | 커스텀 LLM 구현 | VERSION_SPECIFIC | HARD | 높음 | ⬜ |
| SHR-008 | 문서 로더 사용법 | API_USAGE | EASY | 낮음 | ⬜ |
| SHR-009 | 텍스트 분할기 | API_USAGE | MEDIUM | 중간 | ⬜ |
| SHR-010 | 임베딩 모델 연결 | API_USAGE | MEDIUM | 중간 | ⬜ |
| SHR-011 | 벡터스토어 저장/검색 | API_USAGE | MEDIUM | 중간 | ⬜ |
| SHR-012 | 스트리밍 출력 | VERSION_SPECIFIC | MEDIUM | 높음 | ⬜ |
| SHR-013 | 비동기 호출 방식 | VERSION_SPECIFIC | HARD | 높음 | ⬜ |
| SHR-014 | 출력 파서 사용 | API_USAGE | EASY | 낮음 | ⬜ |
| SHR-015 | LCEL vs 체인 개념 비교 | MIGRATION | HARD | 높음 | ⬜ |
| SHR-016 | 도구 정의 방식 | VERSION_SPECIFIC | MEDIUM | 중간 | ⬜ |
| SHR-017 | JSON 출력 강제 | API_USAGE | MEDIUM | 중간 | ⬜ |
| SHR-018 | 허깅페이스 모델 연결 | API_USAGE | MEDIUM | 낮음 | ⬜ |
| SHR-019 | 패키지 설치 방법 | CONCEPT | EASY | 낮음 | ⬜ |
| SHR-020 | 디버그·추적 방법 | VERSION_SPECIFIC | MEDIUM | 중간 | ⬜ |

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

### RET-001: v1.x 커스텀 툴 추가

| 항목 | 값 |
| --- | --- |
| **ID** | `RET-001` |
| **유형** | `API_USAGE` |
| **난이도** | MEDIUM |
| **버전** | v1.x |
| **상태** | 완료 |

**질문**: "LangChain v1.x에서 에이전트에 커스텀 함수 툴을 정의하고 추가하는 방법을 알려줘."

**Gold 섹션**:
- `Agents > Tools > Defining tools`
- `Agents > Tools > Toolkits`

**판정 기준**:
- Hit@K: 위 두 섹션 중 하나라도 Top-K에 포함되면 HIT
- 경계 케이스: v0.3의 `Tool(name=..., func=...)` 패턴이 포함된 청크가 반환되면 버전 혼입으로 E1 측정

#### YAML

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
    - "Agents > Tools > Defining tools"
    - "Agents > Tools > Toolkits"
  note: "@tool 데코레이터와 StructuredTool.from_function 두 경로 모두 허용"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
  is_decoy: false
```

---

### OOS-001: Django ORM ForeignKey (범위 외)

| 항목 | 값 |
| --- | --- |
| **ID** | `OOS-001` |
| **유형** | `OUT_OF_SCOPE` |
| **난이도** | EASY |
| **버전** | null |
| **상태** | 완료 |

**질문**: "Django ORM에서 ForeignKey 관계를 정의하는 방법은?"

**판정 기준**:
- NO_CONTEXT: 반환 `max_score < τ` → LLM 미호출, 안내 메시지 반환
- 합격: "선택한 버전 문서에서 근거를 찾을 수 없습니다" 메시지 반환
- 실패: LLM이 호출되어 Django 내용을 답변하거나, 무관한 LangChain 내용으로 답변

#### YAML

```yaml
question_id: OOS-001
question_set: Q-oos
title: "Django ORM ForeignKey (범위 외)"
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

---

### SHR-001: 에이전트 생성 방식 (v0.3 vs v1.x)

| 항목 | 값 |
| --- | --- |
| **ID** | `SHR-001` |
| **유형** | `VERSION_SPECIFIC` |
| **난이도** | HARD |
| **버전** | both |
| **상태** | 완료 |

**질문**: "LangChain에서 에이전트를 생성하는 방법을 알려줘."

**판정 기준** (E3 블라인드 레이블링):
- 버전 오류 (1): 선택 버전이 v0.3인데 `create_agent()` (v1.x API)가 답변에 포함된 경우, 또는 v1.x인데 `AgentExecutor(agent=..., tools=...)` (v0.3 패턴)이 포함된 경우
- 정상 (0): 선택 버전의 API만 사용하여 답변
- 경계 케이스: 개념 설명만 하고 코드 없는 경우 → 버전 혼입 없으면 0

#### YAML

```yaml
question_id: SHR-001
question_set: Q-shared
title: "에이전트 생성 방식 (v0.3 vs v1.x)"
type: VERSION_SPECIFIC
difficulty: HARD

query: "LangChain에서 에이전트를 생성하는 방법을 알려줘."

versions:
  v0_3:
    target_collection: "langchain_v03_run{id}"
    gold_sections:
      - "Agents > AgentExecutor"
      - "Agents > create_react_agent"
  v1_x:
    target_collection: "langchain_v1x_run{id}"
    gold_sections:
      - "Agents > create_agent"
      - "LangGraph > Agent > Concepts"

label_schema:
  version_error: "0 = 버전 오류 없음 / 1 = 선택한 버전이 아닌 코드·API 포함"
  evidence_quality: "R1·R2 조건만: 0 = 근거 없음 / 1 = 부분 / 2 = 충분"
  answer_usefulness: "0 = 무관 / 1 = 부분 유용 / 2 = 유용"

metadata:
  created_by: "r1nn-dev"
  created_at: "2026-11-04T00:00:00Z"
```

---

## 미결정 사항

- [ ] RET-011~040 질문 목록 완성 (W2 작업)
- [ ] NO_CONTEXT 임계값 τ 결정 (E1 부속 — Q-oos·Q-ret 유사도 분포 측정 후)
- [ ] Q-shared SHR-002~020 gold 섹션 레이블링 완료 (W2 작업)
- [ ] E3 블라인드 레이블링 루브릭 외부 리뷰어와 사전 조율 (W4 이전)

---

*end.*
