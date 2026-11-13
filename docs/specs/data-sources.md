# 데이터 소스 정의

| 항목 | 값 |
| --- | --- |
| **최종 수정** | 2026-11-05 |
| **관련** | `기획서_v1.md` §3 (기술 스택), `claude/protocol.md` E1·E2 (인덱스 빌드 절차), `claude/eval-scenarios.md` Q-ret·Q-oos·Q-shared |

---

## 1. 데이터 한눈에 보기

| 소스 | 종류 | 역할 |
| --- | --- | --- |
| LangChain v0.3 공식 문서 | 공개 GitHub 저장소 (MIT) | v0.3 검색 코퍼스. `langchain_v03_run{id}` Chroma 컬렉션에 적재 |
| LangChain v1.x 공식 문서 | 공개 GitHub 저장소 (MIT) | v1.x 검색 코퍼스. `langchain_v1x_run{id}` Chroma 컬렉션에 적재 |
| 평가 질문셋 Q-ret | 직접 작성 (버전별 10문항) | Retriever 성능 측정 (E2 Hit@K / MRR@K / Precision@K) |
| 평가 질문셋 Q-oos | 직접 작성 (버전별 10문항) | NO_CONTEXT 임계값 τ 결정 (E1) |
| 평가 질문셋 Q-shared | 직접 작성 (공통 20문항) | 버전 간 답변 정확도 비교 (E3) |

- 공식 문서는 외부 ML 데이터셋이 아니라 **검색 코퍼스(retrieval corpus)** 역할을 한다. 모델 학습에는 쓰지 않는다.
- v0.3과 v1.x 코퍼스는 완전히 별개의 Chroma 컬렉션으로 분리한다. 버전 오염을 차단하기 위함이다 (기획서 §4.1 L2 버전 오염 문제).
- 평가 질문셋은 `eval/questions/` 에 버전으로 커밋한다. 실험 도중 질문을 수정하지 않는다.

---

## 2. 로컬 저장 경로 규칙

```
data/
  raw/
    langchain_v03/          # sparse checkout 원본. 수정 금지
      SOURCE.txt            # 저장소 URL, 고정 커밋 SHA, checkout 날짜, 담당자
      docs/docs/            # Docusaurus .md / .mdx 파일
    langchain_v1x/          # sparse checkout 원본. 수정 금지
      SOURCE.txt
      src/oss/              # Mintlify .mdx 파일
      src/snippets/         # 스니펫 컴포넌트 소스 (v1.x snippet expansion에 필요)
  processed/
    langchain_v03/          # 전처리 결과 JSONL. 스크립트로만 생성
      chunks.jsonl
    langchain_v1x/
      chunks.jsonl
eval/
  questions/
    q_ret_v03.jsonl         # Q-ret (v0.3)
    q_ret_v1x.jsonl         # Q-ret (v1.x)
    q_oos_v03.jsonl         # Q-oos (v0.3)
    q_oos_v1x.jsonl         # Q-oos (v1.x)
    q_shared.jsonl          # Q-shared (공통)
```

- `data/`는 Git에 올리지 않는다 (`.gitignore`). **스크립트만 커밋한다.**
  - `scripts/data/checkout_v03.sh` — sparse checkout + SHA 고정
  - `scripts/data/checkout_v1x.sh` — sparse checkout + SHA 고정
  - `scripts/data/preprocess_v03.py` — v0.3 전처리
  - `scripts/data/preprocess_v1x.py` — v1.x 전처리 (snippet expansion 포함)
- 전처리 결과 형식은 **JSONL**. 같은 커밋 SHA에서 같은 스크립트를 재실행하면 동일 결과가 나와야 한다.
- 원본 문서는 GitHub 저장소 이외의 위치에 재배포하지 않는다.

---

## 3. 소스별 상세

### 3.1 LangChain v0.3 공식 문서

| 항목 | 내용 |
| --- | --- |
| **저장소** | `langchain-ai/langchain` |
| **브랜치** | `v0.3` |
| **문서 디렉터리** | `docs/docs/` |
| **파일 형식** | Docusaurus `.md` / `.mdx` |
| **라이선스** | MIT |
| **언어** | 영어 |
| **예상 파일 수** | 약 300–500개 (checkout 후 확인) |

**Sparse Checkout 절차:**

```bash
git clone --filter=blob:none --no-checkout \
    https://github.com/langchain-ai/langchain.git data/raw/langchain_v03
cd data/raw/langchain_v03
git sparse-checkout init --cone
git sparse-checkout set docs/docs
git checkout v0.3           # 브랜치 HEAD 고정
COMMIT_SHA=$(git rev-parse HEAD)
echo "repo=langchain-ai/langchain branch=v0.3 sha=$COMMIT_SHA date=$(date -I) author=$(git config user.name)" \
    > SOURCE.txt
```

- **커밋 SHA는 SOURCE.txt에 기록하고 이 문서 §5 라이선스 표 하단에도 기재한다.**
- 실험 재현 시 동일 SHA로 checkout해야 한다. `git checkout $COMMIT_SHA`

**전처리 절차 (`scripts/data/preprocess_v03.py`):**

1. `docs/docs/` 하위 `.md` / `.mdx` 파일을 재귀 탐색한다.
2. YAML frontmatter 블록 (`---…---`) 을 제거한다.
3. MDX 코드 블록 메타(`:::tip`, `:::note`, `:::js` 등 Docusaurus directive) 를 제거하되, 블록 안의 텍스트 내용은 보존한다.
4. JSX 인라인 태그(`<X />`, `<X>…</X>`)를 제거한다. 단, 코드 블록(` ``` `) 내부는 건드리지 않는다.
5. `.ipynb` 가 같은 디렉터리에 있으면 셀을 순서대로 직렬화한다: `# [code]` / `# [output]` 헤더 뒤에 텍스트를 붙인다.
6. 문서를 **헤딩 단위로 청크 분할**한다 (기본 단위: H2, 보조: H3). 최소 100 토큰, 최대 512 토큰 초과 시 단락 단위 추가 분할.
7. 각 청크에 아래 필드를 부여한다:

| 필드 | 설명 |
| --- | --- |
| `chunk_id` | `{file_stem}_{seq:04d}` |
| `source_key` | `"langchain_v03"` (Chroma 컬렉션 접두사와 일치) |
| `source_file` | 원본 파일의 `docs/docs/`-relative 경로 |
| `heading_path` | `"개요 > 설치 > pip 설치"` 형태의 헤딩 계층 경로 |
| `permalink` | `https://github.com/langchain-ai/langchain/blob/{SHA}/docs/docs/{path}#{anchor}` |
| `text` | 전처리된 청크 텍스트 |
| `token_count` | tiktoken `cl100k_base` 기준 토큰 수 |

8. 출력: `data/processed/langchain_v03/chunks.jsonl` (한 행 = 한 청크)

---

### 3.2 LangChain v1.x 공식 문서

| 항목 | 내용 |
| --- | --- |
| **저장소** | `langchain-ai/docs` |
| **브랜치** | `main` |
| **문서 디렉터리** | `src/oss/` |
| **스니펫 디렉터리** | `src/snippets/` |
| **파일 형식** | Mintlify `.mdx` (JSX 컴포넌트 사용) |
| **라이선스** | MIT |
| **언어** | 영어 |
| **예상 파일 수** | 약 400–600개 (checkout 후 확인) |

**Sparse Checkout 절차:**

```bash
git clone --filter=blob:none --no-checkout \
    https://github.com/langchain-ai/docs.git data/raw/langchain_v1x
cd data/raw/langchain_v1x
git sparse-checkout init --cone
git sparse-checkout set src/oss src/snippets
git checkout main
COMMIT_SHA=$(git rev-parse HEAD)
echo "repo=langchain-ai/docs branch=main sha=$COMMIT_SHA date=$(date -I) author=$(git config user.name)" \
    > SOURCE.txt
```

**전처리 절차 (`scripts/data/preprocess_v1x.py`):**

v0.3과 동일한 1–8단계를 적용하되, 아래 단계를 추가한다.

> **v1.x 전용: Snippet Expansion**
>
> Mintlify는 `<ComponentName />` 형태의 JSX 컴포넌트로 반복 코드 블록을 삽입한다. `src/snippets/` 디렉터리에 컴포넌트 소스가 있다.
>
> 1. `.mdx` 파일에서 `<[A-Z][A-Za-z]+\s*/>` 패턴을 찾는다.
> 2. 컴포넌트 이름을 `src/snippets/` 하위 파일명과 매핑한다 (파일명 대소문자 무시).
> 3. 매핑에 성공하면 태그를 스니펫 본문으로 치환한다.
> 4. 매핑에 실패하면 태그를 제거하고 경고 로그를 남긴다 (`logs/preprocess_v1x_warnings.txt`).

**heading_path 및 permalink 생성 규칙:**

```
permalink = https://github.com/langchain-ai/docs/blob/{SHA}/src/oss/{path}#{anchor}
```

- `anchor` 는 GitHub Markdown 헤딩 앵커 규칙을 따른다 (소문자, 공백→`-`, 특수문자 제거).

---

## 4. 평가 질문셋

평가 질문셋은 **직접 작성**한다. LLM으로 생성하지 않는다 (편향 통제).

| 질문셋 | 파일 | 작성 기준 |
| --- | --- | --- |
| Q-ret (v0.3) | `eval/questions/q_ret_v03.jsonl` | v0.3 문서에 정답이 명확히 존재하는 질문 10개. 각 질문의 정답 청크 ID (`gold_chunk_id`) 기록 |
| Q-ret (v1.x) | `eval/questions/q_ret_v1x.jsonl` | v1.x 문서에 정답이 명확히 존재하는 질문 10개. `gold_chunk_id` 기록 |
| Q-oos (v0.3) | `eval/questions/q_oos_v03.jsonl` | v0.3 문서에 존재하지 않는 주제 (예: v1.x 전용 API). NO_CONTEXT 를 유도해야 한다 |
| Q-oos (v1.x) | `eval/questions/q_oos_v1x.jsonl` | v1.x 문서에 존재하지 않는 주제 (예: 삭제된 v0.3 API) |
| Q-shared | `eval/questions/q_shared.jsonl` | v0.3·v1.x 모두에서 답변 가능한 공통 개념 20개 (E3 비교 실험용). 각 질문에 버전별 `gold_chunk_id` 기록 |

**JSONL 스키마 (Q-ret / Q-shared):**

```json
{
  "id": "v03_ret_001",
  "version": "v0.3",
  "question": "LangChain v0.3에서 ConversationBufferMemory를 사용하려면 어떻게 임포트하나요?",
  "gold_chunk_id": "how_to_add_memory_0003",
  "gold_heading_path": "How-To > Add Memory > ConversationBufferMemory",
  "note": ""
}
```

**JSONL 스키마 (Q-oos):**

```json
{
  "id": "v03_oos_001",
  "version": "v0.3",
  "question": "LangGraph Studio에서 그래프를 시각적으로 디버깅하는 방법은?",
  "expected_behavior": "NO_CONTEXT",
  "note": "LangGraph Studio는 v1.x 이후에 등장. v0.3 문서에 없음"
}
```

---

## 5. 라이선스 확인 사항

| 소스 | 라이선스 | 확인 상태 |
| --- | --- | --- |
| `langchain-ai/langchain` v0.3 문서 | MIT | GitHub `LICENSE` 파일 확인 필요 (미결 D-1) |
| `langchain-ai/docs` main 문서 | MIT | GitHub `LICENSE` 파일 확인 필요 (미결 D-1) |

- 두 저장소 모두 MIT 라이선스로 공개되어 있으며, 비상업적·교육·연구 목적 사용에 제한이 없다.
- **보고서·발표 자료**에 LangChain 공식 문서를 출처로 표기한다.
- 고정된 커밋 SHA는 아래 표에 checkout 완료 후 기재한다.

| 저장소 | 브랜치 | 고정 커밋 SHA | Checkout 날짜 |
| --- | --- | --- | --- |
| `langchain-ai/langchain` | `v0.3` | (미결 D-2) | - |
| `langchain-ai/docs` | `main` | (미결 D-2) | - |

---

## 미결 사항

- [ ] **D-1** 각 저장소의 `LICENSE` 파일 원문 확인 후 라이선스 표 갱신
- [ ] **D-2** Sparse checkout 실행 후 고정 커밋 SHA를 이 문서 §5 표와 `SOURCE.txt` 에 기록
- [ ] **D-3** v0.3 `docs/docs/` 파일 수·토큰 총량 확인 (청크 수 예측, Chroma 메모리 예산 검증)
- [ ] **D-4** v1.x `src/snippets/` 컴포넌트 목록과 `.mdx` 내 참조 현황 확인 (매핑 실패율 추정)
- [ ] **D-5** heading_path 에서 비 ASCII 문자(한국어 혼재 여부) 처리 규칙 확정
- [ ] **D-6** `.ipynb` 파일 존재 여부 확인 (특히 v0.3 `how-to/` 계열)
- [ ] **D-7** Q-ret / Q-oos / Q-shared 질문셋 작성 완료 (E1·E2·E3 실험 전에 커밋)

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | §3.1·§3.2 청크 메타데이터 `version` 필드 → `source_key` 로 통일 |

---

end.
