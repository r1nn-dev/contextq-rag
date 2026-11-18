# 데이터 소스 정의

| 항목 | 값 |
| --- | --- |
| **최종 수정** | 2026-11-18 |
| **관련** | `docs/planning/policy.md` §3 소스·버전 정책 · §4 인덱스 정책 · §10.1 IngestRun, `docs/specs/doc-source.md` (전처리 규칙), `docs/experiments/protocol.md` E1·E2 |

---

## 1. 데이터 한눈에 보기

| 소스 | 종류 | 역할 |
| --- | --- | --- |
| LangChain v0.3 공식 문서 | 공개 GitHub 저장소 (MIT) | v0.3 검색 코퍼스. run마다 `langchain_v03_run{id}` Chroma 컬렉션에 적재 |
| LangChain v1.x 공식 문서 | 공개 GitHub 저장소 (MIT) | v1.x 검색 코퍼스. run마다 `langchain_v1x_run{id}` Chroma 컬렉션에 적재 |
| 평가 질문셋 Q-ret | AI 초안 + 사람 검수 (40문항, 버전별 20) | 검색 품질·혼입 측정 (E1 혼입률, E2 Hit@K / MRR@K / Precision@K) |
| 평가 질문셋 Q-oos | AI 초안 + 사람 검수 (10문항) | NO_CONTEXT 임계값 τ 결정 (E1) |
| 평가 질문셋 Q-shared | AI 초안 + 사람 검수 (공통 20문항 × 2버전) | 버전 간 답변 정확도 비교 (E3) |

- 공식 문서는 외부 ML 데이터셋이 아니라 **검색 코퍼스(retrieval corpus)** 역할을 한다. 모델 학습에는 쓰지 않는다.
- 수집 대상(저장소·ref·문서 경로·포맷·Adapter)은 `ai.sources` 카탈로그가 소유한다. 이 문서는 카탈로그 값의 근거와 포함·제외 경로를 기록한다.
- v0.3과 v1.x 코퍼스는 run 단위로 분리된 별개의 Chroma 컬렉션에 적재한다(ADR-004).
- 평가 질문셋은 `eval/questions/` 에 커밋하고 `eval-v1` 태그로 고정한다. 태그 이후에는 질문을 수정하지 않는다(`docs/experiments/protocol.md` §0.2).

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
  snapshots/                   # make snapshot-index 산출물 — S3에 run별 보관 (정책서 §4.5)
    snapshot-{source_key}-run{id}.tar.gz
    snapshot-{source_key}-run{id}.tar.gz.sha256
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

### 3.3 코퍼스 규모와 임베딩 비용

수집 커밋 v0.3 `9971fd8`, v1.x `39276c9` 기준 측정값이다(2026-11-17). 토큰은 `text-embedding-3-small`과 같은 토크나이저(`cl100k_base`)로 센 청크 토큰 합이고, 비용은 단가 $0.02 / 1M 토큰(`ai-server/configs/models.yaml`)으로 계산했다.

| 소스 | 포함 파일 | 섹션 | 전략 | 청크 | 토큰 | 임베딩 비용 |
| --- | --- | --- | --- | --- | --- | --- |
| v0.3 | 225 (ipynb 170) | 1,368 | A | 2,392 | 370,839 | $0.007417 |
| v0.3 | | | B | 2,496 | 372,457 | $0.007449 |
| v0.3 | | | C | 2,128 | 350,408 | $0.007008 |
| v1.x | 66 (문서 64) | 632 | A | 1,610 | 270,079 | $0.005402 |
| v1.x | | | B | 1,715 | 273,587 | $0.005472 |
| v1.x | | | C | 1,361 | 255,854 | $0.005117 |
| 합계 | | | 3전략 × 2소스 | 11,702 | 1,893,224 | **$0.037864** |

- 실제 run의 `ingest_runs.embedding_tokens`·`embedding_cost_usd`는 API 응답 사용량으로 기록한다. 같은 SHA·전략이면 위 값과 거의 같아야 한다.
- 소스 문서가 바뀌면(새 SHA) 표를 다시 측정한다.

---

## 4. 평가 질문셋

평가 질문셋은 **AI가 초안을 쓰고 사람이 검수**한다. 검수하지 않은 문항은 실험에 쓰지 않는다.

| 질문셋 | 파일 | 작성 기준 |
| --- | --- | --- |
| Q-ret | `eval/questions/RET/RET-{번호}.yaml` (40개) | 버전별 20개. 해당 버전 문서에 정답이 명확히 있는 질문. 디코이 10개(버전별 5개)는 버전을 명시하지 않아 양쪽 버전 청크가 경쟁하도록 쓴다 |
| Q-oos | `eval/questions/OOS/OOS-{번호}.yaml` (10개) | 두 버전 문서 모두에 없는 주제. NO_CONTEXT를 유도해야 한다 |
| Q-shared | `eval/questions/SHR/SHR-{번호}.yaml` (20개) | v0.3·v1.x 모두에서 답변 가능한 공통 주제. 버전별 정답 위치 기록 |

- 스키마·ID 규칙·gold 기록 규칙은 `docs/experiments/eval-scenarios.md` §2·§3을 따른다. 질문 1개 = YAML 파일 1개.
- `chunk_id`는 청킹 전략·파라미터마다 달라지므로(정책서 §4.1) 정답은 청크 ID가 아니라 `{file_path, heading_path}`로 기록한다. gold는 ACTIVE 인덱스(§5 표의 run)에 있는 섹션만 쓴다.
- **검수 절차**: 사람이 문항마다 (1) 질문이 해당 버전 사용자가 실제로 물을 만한지, (2) gold 섹션에 답이 있는지, (3) 다른 섹션에 더 나은 답이 있지 않은지 확인하고 `metadata.reviewed_by`를 채운다. 모든 문항의 `reviewed_by`가 채워진 커밋에 `eval-v1` 태그를 단다.
- **타당성 위협**: 질문을 LLM이 초안 작성하면 문서 표현과 비슷한 질문이 많아져 검색 지표가 높게 나올 수 있다(편향). 보고서 실험 절에 이 위협과 사람 검수로 완화한 방법을 적는다.

---

## 5. 라이선스 확인 사항

| 소스 | 라이선스 | 확인 상태 |
| --- | --- | --- |
| `langchain-ai/langchain` v0.3 문서 | MIT (`Copyright (c) LangChain, Inc.`) | 저장소 루트 `LICENSE` 확인 (2026-11-17) |
| `langchain-ai/docs` main 문서 | MIT (`Copyright (c) 2025 LangChain`) | 저장소 루트 `LICENSE` 확인 (2026-11-17) |

- **보고서·발표 자료**에 LangChain 공식 문서를 출처로 표기한다.
- ACTIVE로 활성화한 run의 커밋 SHA를 아래 표에 기록한다. SHA의 원본은 `ai.ingest_runs.commit_sha`다.

| 저장소 | ref | ACTIVE run | 커밋 SHA | 수집일 | 청크(전략 C) | 임베딩 비용 |
| --- | --- | --- | --- | --- | --- | --- |
| `langchain-ai/langchain` | `v0.3` | 6 | `9971fd8caafcfddddc94492cdecb02ce67b82da6` | 2026-11-18 | 2,128 | $0.007008 |
| `langchain-ai/docs` | `main` | 10 | `9d9747d0cf241e086c616a16d5ce230ad8f8f31d` | 2026-11-18 | 1,364 | $0.005130 |

- 2026-11-18 E2 확정으로 전략 B run(1·3)에서 전략 C run(6·10)으로 교체했다. 이전 기록: run 1(`9971fd8`, 2,496청크)·run 3(`db05d5c`, 1,715청크).

- 라인 앵커 확인(2026-11-17, ACTIVE run에서 `.md`·`.mdx` 청크 20건 표본): 섹션 일치 18/20. 나머지 2건은 내용 전체가 스니펫에서 펼쳐진 청크라 앵커가 원문의 스니펫 태그 줄을 가리킨다(`docs/specs/doc-source.md` §4.2 설계대로).

---

## 미결 사항

- [x] **D-2** 두 소스 ACTIVE run의 커밋 SHA를 §5 표에 기록 (2026-11-17)
- [ ] **D-5** heading_path 에서 비 ASCII 문자 처리 규칙 확정 (현재 두 소스 모두 영어 문서)
- [ ] **D-7** Q-ret / Q-oos / Q-shared 질문셋 작성 완료 (E1·E2·E3 실험 전에 커밋)

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | §3.1·§3.2 청크 메타데이터 `version` 필드 → `source_key` 로 통일 |
| v0.3 | 수집을 `make ingest`(sparse checkout, run 단위)로 정리, 포함·제외 경로 확정, 수집 스크립트·JSONL 산출물 제거, 청크 필드는 정책서 §4.2로 일원화, 라이선스 확인(D-1), 파일 수·`.ipynb` 존재 확인(D-3·D-4·D-6은 각 Adapter 작업에서 측정) |
| v0.4 | §4 평가 질문셋: 질문 1개 = YAML 1개, 문항 수(Q-ret 40·Q-oos 10·Q-shared 20), 작성 주체를 AI 초안 + 사람 검수로 변경, gold 기록 단위 |

---

end.
