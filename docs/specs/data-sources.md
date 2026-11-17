# 데이터 소스 정의

| 항목 | 값 |
| --- | --- |
| **최종 수정** | 2026-11-17 |
| **관련** | `docs/planning/policy.md` §3 소스·버전 정책 · §4 인덱스 정책 · §10.1 IngestRun, `docs/specs/doc-source.md` (전처리 규칙), `docs/experiments/protocol.md` E1·E2 |

---

## 1. 데이터 한눈에 보기

| 소스 | 종류 | 역할 |
| --- | --- | --- |
| LangChain v0.3 공식 문서 | 공개 GitHub 저장소 (MIT) | v0.3 검색 코퍼스. run마다 `langchain_v03_run{id}` Chroma 컬렉션에 적재 |
| LangChain v1.x 공식 문서 | 공개 GitHub 저장소 (MIT) | v1.x 검색 코퍼스. run마다 `langchain_v1x_run{id}` Chroma 컬렉션에 적재 |
| 평가 질문셋 Q-ret | 직접 작성 (버전별 10문항) | Retriever 성능 측정 (E2 Hit@K / MRR@K / Precision@K) |
| 평가 질문셋 Q-oos | 직접 작성 (버전별 10문항) | NO_CONTEXT 임계값 τ 결정 (E1) |
| 평가 질문셋 Q-shared | 직접 작성 (공통 20문항) | 버전 간 답변 정확도 비교 (E3) |

- 공식 문서는 외부 ML 데이터셋이 아니라 **검색 코퍼스(retrieval corpus)** 역할을 한다. 모델 학습에는 쓰지 않는다.
- 수집 대상(저장소·ref·문서 경로·포맷·Adapter)은 `ai.sources` 카탈로그가 소유한다. 이 문서는 카탈로그 값의 근거와 포함·제외 경로를 기록한다.
- v0.3과 v1.x 코퍼스는 run 단위로 분리된 별개의 Chroma 컬렉션에 적재한다(ADR-004).
- 평가 질문셋은 `eval/questions/` 에 버전으로 커밋한다. 실험 도중 질문을 수정하지 않는다.

---

## 2. 수집 방식과 로컬 저장 경로

수집은 `make ingest SOURCE=<source_key>`가 실행한다(ADR-005). local·staging 프로필에서 `INGEST_ENABLED=true`일 때만 명령이 등록된다(INV-17).

1. `ingest_runs`에 PENDING run을 만든다.
2. COLLECTING으로 전이하고 카탈로그의 `repo_url`·`ref`·`doc_path`로 sparse checkout을 실행한다.
   - 매 run 새로 받는다(`--depth 1 --filter=blob:none`). 이전 run 파일이 섞이지 않는다.
   - 체크아웃한 커밋의 40자 SHA를 `ingest_runs.commit_sha`에 기록한다(ADR-007).
3. 실패하면 FAILED로 전이하고 `failure_stage`·`failure_reason`을 기록한다. 기존 ACTIVE run은 건드리지 않는다(RAG-10).

```
${INGEST_DATA_DIR}/            # 기본값 ./data (ai-server 기준). Git에 올리지 않는다
  raw/
    langchain_v03/             # 체크아웃 원본. 수정 금지. run마다 새로 받는다
      SOURCE.txt               # repo, ref, sha, 수집 시각(UTC)
      docs/docs/
    langchain_v1x/
      SOURCE.txt
      src/oss/
      src/snippets/            # 스니펫 확장용 (Mintlify)
  reports/
    run{id}/                   # run별 산출 리포트 (예: missing_snippets.csv)
```

- `data/`는 `.gitignore` 대상이다. 코드(`ai-server/src/ingest/`)만 커밋한다.
- 같은 커밋 SHA에서 같은 청킹 파라미터로 다시 실행하면 같은 `chunk_id` 집합이 나와야 한다(INV-04).
- 원본 문서는 GitHub 저장소 이외의 위치에 재배포하지 않는다.

---

## 3. 소스별 상세

### 3.1 LangChain v0.3 공식 문서 (`langchain_v03`)

| 항목 | 내용 |
| --- | --- |
| **저장소** | `langchain-ai/langchain` |
| **ref** | `v0.3` (브랜치) |
| **문서 디렉터리** | `docs/docs/` |
| **체크아웃 경로** | `docs/docs/` |
| **파일 형식** | Docusaurus `.mdx` / `.md` / `.ipynb` |
| **Adapter** | `DocusaurusAdapter` |
| **라이선스** | MIT |

**포함 경로** (정책서 §3.2 포함 범위: 개념·튜토리얼·how-to·마이그레이션 가이드)

| 경로 (`docs/docs/` 기준) | 내용 |
| --- | --- |
| `concepts/**` | 개념 가이드 |
| `how_to/**` | how-to 가이드 |
| `tutorials/**` | 튜토리얼 |
| `versions/**` | 마이그레이션 가이드(v0.2·v0.3, chains·memory 이전), 릴리스 정책 |
| `troubleshooting/**` | 오류 해결 가이드 |
| `introduction.mdx` | 소개 |

**제외 경로**

| 경로 | 사유 |
| --- | --- |
| `integrations/**` | 수백 개 제공자 페이지. 버전 단절 학습과 무관, 레이블링 비용 과다 (정책서 §3.2) |
| `contributing/**`, `additional_resources/**`, `changes/**`, `people.mdx` | 개념·how-to 범위 밖 |
| `_templates/**`, `example_data/**` | 문서 아님 |

### 3.2 LangChain v1.x 공식 문서 (`langchain_v1x`)

| 항목 | 내용 |
| --- | --- |
| **저장소** | `langchain-ai/docs` |
| **ref** | `main` (수집 시점 커밋 SHA로 고정, 정책서 §3.2 버전 의미) |
| **문서 디렉터리** | `src/oss/` |
| **체크아웃 경로** | `src/oss/`, `src/snippets/` |
| **파일 형식** | Mintlify `.mdx` (JSX 컴포넌트, 스니펫 import, `:::python`/`:::js` 조건부 블록) |
| **Adapter** | `MintlifyAdapter` |
| **라이선스** | MIT |

**포함 경로**

| 경로 (`src/oss/` 기준) | 내용 |
| --- | --- |
| `langchain/**` | LangChain v1 개념·how-to·튜토리얼 (아래 제외 경로 빼고) |
| `concepts/**` | 공통 개념 가이드 |
| `python/migrate/langchain-v1.mdx` | v1 마이그레이션 가이드 (정책서 §3.2 필수) |
| `common-errors.mdx`, `versioning.mdx`, `release-policy.mdx` | 오류·버전 정책 (v0.3 `troubleshooting`·`versions`와 대응) |

**제외 경로**

| 경로 | 사유 |
| --- | --- |
| `javascript/**`, `langchain/frontend/**` | JS/TS 전용 문서 (정책서 §3.2 수집 언어: Python만) |
| `langgraph/**`, `python/migrate/langgraph-*.mdx` | `langgraph` 패키지 문서 — 별도 버전 체계 (정책서 §3.2) |
| `deepagents/**`, `python/migrate/langchain-mcp-adapters.mdx` | 별도 패키지 문서 — v0.3 ↔ v1.x 비교 프레이밍과 무관 |
| `integrations/**`, `python/integrations/**` | 제공자 페이지 (정책서 §3.2) |
| `python/releases/**`, `langchain/changelog-*.mdx` | 릴리스 노트 (정책서 §3.2) |
| `reference/**` | API Reference (정책서 §3.2) |
| `contributing/**`, `openwiki/**`, `learn.mdx`, `security-policy.mdx`, `python/studio.mdx` | 개념·how-to 범위 밖 |

- 공용 페이지의 `:::js` 블록은 내용까지 제거하고 `:::python` 블록은 마커만 제거한다(정책서 §4.3).

---

## 4. 평가 질문셋

평가 질문셋은 **직접 작성**한다. LLM으로 생성하지 않는다 (편향 통제).

| 질문셋 | 파일 | 작성 기준 |
| --- | --- | --- |
| Q-ret (v0.3) | `eval/questions/q_ret_v03.jsonl` | v0.3 문서에 정답이 명확히 존재하는 질문 10개. 정답 위치(파일·heading_path) 기록 |
| Q-ret (v1.x) | `eval/questions/q_ret_v1x.jsonl` | v1.x 문서에 정답이 명확히 존재하는 질문 10개. 정답 위치 기록 |
| Q-oos (v0.3) | `eval/questions/q_oos_v03.jsonl` | v0.3 문서에 존재하지 않는 주제 (예: v1.x 전용 API). NO_CONTEXT 를 유도해야 한다 |
| Q-oos (v1.x) | `eval/questions/q_oos_v1x.jsonl` | v1.x 문서에 존재하지 않는 주제 (예: 삭제된 v0.3 API) |
| Q-shared | `eval/questions/q_shared.jsonl` | v0.3·v1.x 모두에서 답변 가능한 공통 개념 20개 (E3 비교 실험용). 버전별 정답 위치 기록 |

> `chunk_id`는 청킹 전략·파라미터마다 달라지므로(정책서 §4.1) 정답은 청크 ID가 아니라 파일 경로·heading_path로 기록한다. 질문셋 스키마는 평가 질문셋 작업(R-3-1)에서 확정한다.

---

## 5. 라이선스 확인 사항

| 소스 | 라이선스 | 확인 상태 |
| --- | --- | --- |
| `langchain-ai/langchain` v0.3 문서 | MIT (`Copyright (c) LangChain, Inc.`) | 저장소 루트 `LICENSE` 확인 (2026-11-17) |
| `langchain-ai/docs` main 문서 | MIT (`Copyright (c) 2025 LangChain`) | 저장소 루트 `LICENSE` 확인 (2026-11-17) |

- **보고서·발표 자료**에 LangChain 공식 문서를 출처로 표기한다.
- ACTIVE로 활성화한 run의 커밋 SHA를 아래 표에 기록한다. SHA의 원본은 `ai.ingest_runs.commit_sha`다.

| 저장소 | ref | ACTIVE run | 커밋 SHA | 수집일 |
| --- | --- | --- | --- | --- |
| `langchain-ai/langchain` | `v0.3` | | | |
| `langchain-ai/docs` | `main` | | | |

---

## 미결 사항

- [ ] **D-2** 두 소스 ACTIVE run의 커밋 SHA를 §5 표에 기록 (인덱스 검증 게이트·활성화 작업 완료 시)
- [ ] **D-5** heading_path 에서 비 ASCII 문자 처리 규칙 확정 (현재 두 소스 모두 영어 문서)
- [ ] **D-7** Q-ret / Q-oos / Q-shared 질문셋 작성 완료 (E1·E2·E3 실험 전에 커밋)

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | §3.1·§3.2 청크 메타데이터 `version` 필드 → `source_key` 로 통일 |
| v0.3 | 수집을 `make ingest`(sparse checkout, run 단위)로 정리, 포함·제외 경로 확정, 수집 스크립트·JSONL 산출물 제거, 청크 필드는 정책서 §4.2로 일원화, 라이선스 확인(D-1), 파일 수·`.ipynb` 존재 확인(D-3·D-4·D-6은 각 Adapter 작업에서 측정) |

---

end.
