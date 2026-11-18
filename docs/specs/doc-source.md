# 문서 수집 및 전처리 명세

> **최종 수정**: 2026-11-17

---

## 1. 개요

- **목적**: v0.3 Docusaurus(`.md`·`.mdx`·`.ipynb`)와 v1.x Mintlify(`.mdx`) 두 포맷을 하나의 정규화 문서(`NormalizedDocument`)로 통일하는 Source Adapter의 전처리 규칙과 필드 도출 규칙을 정한다.
- **범위**: 파일 선택, 전처리, 섹션 분리, 청크 필드 도출. 수집 절차·포함/제외 경로는 `docs/specs/data-sources.md`, 정책 원본은 `docs/planning/policy.md` §4, 타입 계약은 `docs/specs/interfaces.md` §2.1을 따른다.
- **설계 원칙**: 청킹·임베딩·검색 계층은 소스 포맷을 몰라야 한다. Adapter가 포맷 차이를 흡수해 `NormalizedDocument`를 돌려준다(ADR-006).
- **코드 위치**: `ai-server/src/adapters/` (Adapter), `ai-server/src/domain/documents.py` (모델).

---

## 2. NormalizedDocument

타입 정의는 `docs/specs/interfaces.md` §2.1이 원본이다.

| 필드 | 내용 |
| --- | --- |
| `file_path` | 저장소 루트 기준 경로. 예: `src/oss/langchain/agents.mdx`, `docs/docs/how_to/tools.ipynb` |
| `title` | frontmatter `title` → 첫 H1 → 파일 stem 순으로 정한다 |
| `doc_type` | `md` / `mdx` / `ipynb` |
| `site_url` | 공식 문서 사이트 URL. 보조 링크이며 불변을 보장하지 않는다 |
| `sections` | 문서 순서대로의 `Section` 목록 |
| `Section.heading_path` | `"Agents > Tools > Defining tools"` (§5) |
| `Section.text` | 전처리 완료 본문. 섹션 헤더 줄을 포함한다 |
| `Section.line_numbers` | `text` 각 줄의 원문 라인 번호(1부터). 라인 앵커 permalink의 근거 |

---

## 3. Source Adapter

```python
class SourceAdapter(Protocol):
    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        """체크아웃 루트(저장소 루트) 아래 포함 경로의 문서를 전처리해 순회한다."""
```

| Adapter | 카탈로그 `adapter_class` | 문서 루트 | 비고 |
| --- | --- | --- | --- |
| `DocusaurusAdapter` | `DocusaurusAdapter` | `docs/docs/` | v0.3 |
| `MintlifyAdapter` | `MintlifyAdapter` | `src/oss/` | v1.x, 스니펫 루트 `src/snippets/` |

- 파이프라인은 카탈로그의 `adapter_class` 이름으로 Adapter를 고른다. 등록되지 않은 이름이면 PROCESSING 단계 실패다.
- Adapter는 전처리 부산물(누락 스니펫 목록 등)을 리포트로 함께 돌려준다. 파이프라인이 `reports/run{id}/`에 저장한다.

---

## 4. 전처리 규칙

모든 처리는 **원문 라인 번호를 단 줄 단위**로 한다. 줄을 지우거나 펼쳐도 남은 줄은 원래 라인 번호를 유지한다.

### 4.1 공통

| 순서 | 대상 | 처리 |
| --- | --- | --- |
| 1 | frontmatter (`---` … `---`, 파일 첫 줄부터) | 제거. `title`은 문서 제목으로 사용 |
| 2 | 코드 펜스 (```` ``` ````·`~~~`, 들여쓰기 허용) | 펜스 줄과 내부 줄은 어떤 규칙도 적용하지 않는다(내부 diff 0) |
| 3 | 인라인 코드 (`` `…` ``) | 태그 제거 대상에서 제외 |
| 4 | MDX `import … from '…'` / `export …` 줄 (펜스 밖, 줄 시작) | 줄 삭제 |
| 5 | JSX 주석 `{/* … */}` (여러 줄 가능) | 삭제 |
| 6 | 대문자로 시작하는 JSX 태그, HTML 태그(`img`·`br`·`div`·`table` 등) | 태그만 지우고 텍스트 자식은 남김. 여러 줄에 걸친 태그는 닫힐 때까지 지움 |
| 7 | 태그의 `title="…"`·`label="…"` 속성 (`Tab`·`Step`·`Accordion`·`Card`·`TabItem` 등) | 속성 값을 텍스트 줄로 남김 |
| 8 | 빈 줄 (펜스 밖) | 연속 빈 줄은 1줄로 줄임 |

### 4.2 Mintlify (v1.x)

| 대상 | 처리 | 자동 검사 |
| --- | --- | --- |
| `:::python` … `:::` | 마커 줄만 제거, 내용 보존 | — |
| `:::js` … `:::` | 내용까지 제거 | `:::js` 잔존 0건 (RAG-03) |
| 스니펫: `import X from '/snippets/…'` + `<X />` | 태그 줄을 스니펫 본문(같은 전처리 적용)으로 펼침. 펼친 줄은 태그 줄의 라인 번호를 갖는다 | — |
| 스니펫 파일 없음 | 태그 제거 + 누락 목록(`missing_snippets.csv`: 파일, 컴포넌트, import 경로) 기록 | 누락 비율 산출 |
| API 참조 `@[`name`]` · `@[name]` | `` `name` `` · `name` 으로 치환 | — |

- 스니펫 경로 `/snippets/…`는 `src/snippets/…`로 해석한다.
- `site_url`: `https://docs.langchain.com/oss/python/{문서 루트 기준 경로, 확장자 제외}` (`python/` 하위 문서는 접두어 중복 제거).

### 4.3 Docusaurus (v0.3)

| 대상 | 처리 | 자동 검사 |
| --- | --- | --- |
| admonition `:::tip`·`:::note`·`:::info`·`:::important`·`:::warning`·`:::caution`·`:::danger` | 마커 줄만 제거, 내용 보존. 제목(`:::info 제목`·`:::tip[제목]`)은 텍스트 줄로 남김 | 마커 잔존 0건 |
| `.ipynb` | markdown·code·raw 셀을 셀 순서대로 빈 줄로 이어 직렬화. 출력 셀 제거. code 셀은 ```` ```python ```` 펜스로 감쌈. 첫 raw 셀의 frontmatter는 문서 frontmatter로 처리하고, 그 밖의 raw 셀은 markdown과 같이 전처리 | 출력 셀 잔존 0건 |
| `.ipynb` 라인 번호 | 직렬화한 텍스트 기준 줄 번호(1부터). permalink는 파일 단위(라인 앵커 없음, ADR-007) | — |

- `site_url`: `https://python.langchain.com/v0.3/docs/{문서 루트 기준 경로, 확장자 제외}/`.

---

## 5. 섹션 분리와 heading_path

- 펜스 밖의 H1~H3(`#`~`###`) 줄이 새 섹션을 시작한다. H4 이하는 섹션 안 본문으로 남는다.
- 첫 헤더 앞 본문은 문서 제목을 heading_path로 하는 섹션이 된다.
- 문서에 H1이 없으면 문서 제목을 최상위 경로로 쓴다. `heading_path = " > ".join([제목 또는 H1, H2, H3])` (해당 레벨까지).
- 헤더 텍스트 정제: 양끝 공백, 인라인 마크다운(`**`, `__`, `` ` ``), 명시 앵커(`{#id}`) 제거.
- 레벨 스킵(H1 → H3)은 있는 레벨만 잇는다.
- **본문 50자 미만 섹션**(헤더 줄 제외, 공백 제거 기준)은 청크를 만들지 않고 **바로 앞 섹션에 병합**한다. 첫 하위 섹션이면 곧 상위 섹션이며, 병합 후에도 라인 범위가 연속이다(정책서 §4.3). 문서의 첫 섹션이면 다음 섹션과 합친다.

---

## 6. 청크 분할

전략은 E2 비교 대상 3종이며 파라미터는 `ai-server/configs/ingest.yaml`에서 읽는다(`docs/experiments/protocol.md` E2).

| 전략 | 방식 | 코드 펜스 |
| --- | --- | --- |
| A | `CharacterTextSplitter` | 사후 검사로 분할 건수 보고 |
| B | `RecursiveCharacterTextSplitter` | 사후 검사로 분할 건수 보고 |
| C | 구조 인식: H2 단위로 섹션을 묶고(`header_levels=["#","##"]`), 상한 초과 시 문단 경계에서 분할, 코드 펜스는 원자 단위 | 분할 금지 |

- 전략 A·B는 섹션 단위로 분할기를 적용한다. 청크는 섹션 경계를 넘지 않고 `heading_path`는 그 섹션의 값이다.
- 전략 C는 같은 H2 아래의 H3 섹션을 H2 섹션에 이어 붙인 묶음 단위로 분할한다. `heading_path`는 묶음 첫 섹션(H2 또는 그 위)의 값이다.
- 크기 단위는 문자다(`chunk_size=1000`, LangChain 분할기 기본 단위). 전략 C는 코드 펜스 하나가 상한보다 크면 그 펜스만으로 청크 하나를 만든다.
- 청크의 `line_start`·`line_end`는 청크 첫 줄·마지막 줄의 `Section.line_numbers` 값이다.
- 공백 제외 50자 미만 청크는 만들지 않는다. 같은 섹션(전략 C는 묶음)의 바로 앞 청크에, 첫 청크면 다음 청크에 병합한다(정책서 §4.3 "50자 미만 청크 0건"). 병합으로 상한을 조금 넘을 수 있다.
- 코드 펜스 분할 판정은 청크 끝에서 펜스가 열려 있는지로 한다(펜스 안 문자열의 ```` ``` ````는 닫는 펜스가 아니다).
- 기본 전략은 E2로 확정한 전략 C다(`configs/ingest.yaml` `default_strategy`, `eval/results/E2/decision.md`). `make ingest SOURCE=… STRATEGY=…`로 바꿀 수 있고, 전략별 결과는 서로 다른 run이다(정책서 §4.1).
- A·B의 코드 펜스 분할 건수와 전략별 청크 통계는 `reports/run{id}/chunking.json`에 남긴다(E2 보고 항목).

---

## 7. 필드 도출 규칙

필수 필드 목록은 정책서 §4.2가 원본이다.

| 필드 | 규칙 |
| --- | --- |
| `chunk_id` | `sha256(source_key, commit_sha, file_path, heading_path, chunk_index, chunk_strategy, chunk_params_hash)` 앞 32자. 필드는 구분자 `\x1f`로 잇는다. `chunk_index`는 파일 안 청크 순서(0부터) (INV-04) |
| `permalink` | `https://github.com/{repo}/blob/{commit_sha}/{file_path}?plain=1#L{line_start}-L{line_end}`. `.ipynb`는 `?plain=1#…` 없이 파일 단위 (ADR-007, INV-05) |
| `token_count` | `tiktoken` `cl100k_base` 토큰 수 |
| `has_code` | 청크에 코드 펜스가 있으면 true |

---

## 8. 신규 소스 추가 절차

1. `docs/specs/data-sources.md`에 저장소·ref·경로·포함/제외 경로·라이선스를 추가한다.
2. 포맷이 새로우면 `SourceAdapter`를 구현하고 Adapter 레지스트리에 등록한다. 기존 포맷이면 Adapter를 재사용한다.
3. Alembic 데이터 리비전으로 `ai.sources` 카탈로그 행을 추가한다(UI·코드에 버전 문자열을 하드코딩하지 않는다).
4. `eval/questions/`에 새 버전 Q-ret / Q-oos 질문셋을 추가한다.

---

## 미결 사항

- [ ] **DS-4** heading_path의 비 ASCII 문자 처리 규칙 — `data-sources.md` D-5와 연동 (현재 두 소스 모두 영어 문서)
- [ ] **DS-5** 전략 A·B·C 파라미터 최종값 — E2(R-7-3) 결과로 확정

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | `NormalizedDocument.version` → `source_key` (통일된 소스 식별자); `RetrievedChunk.score` → `similarity` (API 계약 일치) |
| v0.3 | 정책서 §4·인터페이스 명세 v0.3 기준으로 재작성: `NormalizedDocument`를 Adapter 출력(섹션·원문 라인 번호)으로 변경, 줄 단위 전처리, `:::python`/`:::js`·스니펫·API 참조 규칙, 노트북 직렬화, 50자 미만 병합, 청킹 전략 A·B·C, `chunk_id` 해시 규칙, 라인 앵커 permalink |

---

*end.*
