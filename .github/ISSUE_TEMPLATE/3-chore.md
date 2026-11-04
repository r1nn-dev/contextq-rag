---
name: 일반 작업
about: 문서, 설정, 테스트, 리팩터링 등 기능 구현이 아닌 작업을 등록합니다.
title: "chore(<scope>): "
labels: chore
assignees: ""
---

<!--
[AI 작성 안내]

이 템플릿은 문서·설정·테스트·리팩터링·성능 개선 등 기능 구현 이외의 작업용이다.
type은 실제 작업 성격에 맞게 chore / docs / test / refactor / perf / style 중에서 고른다.

제목 형식: <type>(<scope>): <한 줄 요약>
- 예: chore(ci): GitHub Actions CI 워크플로우 초안 작성
- 예: chore(infra): Docker Compose 전체 스택 초안
- 예: chore(deps): langchain 0.3.7 → 0.4.0 업그레이드
- 예: docs(adr): 0001 Vector DB 선택 (Chroma vs Weaviate) ADR 추가
- 예: test(rag): 버전 필터 조건 단위 테스트 추가
- 예: perf(retrieval): 단일 의미 검색 → 하이브리드 검색으로 precision@3 개선
- 예: perf(rag): 시스템 프롬프트 개선으로 faithfulness 개선

각 섹션을 채울 때 기준:
- "작업 목적": 문제→작업→개선 흐름으로 쓴다. "한다"가 아니라 "이래서 문제이므로 이렇게 한다".
- "측정 기준": perf 이슈라면 필수. 그 외에는 삭제한다. "빨라진다"는 기준이 될 수 없다.
- 선택 섹션에 내용이 없으면 섹션 전체를 삭제한다.
- 코드·명령어·파일 경로·함수명·테이블명은 반드시 `코드블록`으로 감싼다.

게시 전 삭제: 모든 HTML 주석블록 전체를 삭제한다.
-->

## 🎯 작업 목적

<!--
"~를 한다"가 아니라 "~이 문제이므로 ~를 해서 ~를 개선한다"처럼 쓴다.
변경하면 안 되는 범위도 명시한다.

이 프로젝트 맥락 예시:
CI 설정: PR 생성 시 ruff lint·타입 검사·단위 테스트·gitleaks 비밀값 스캔이 자동으로 돌지 않아 코드 품질 기준 위반이 병합 이후에야 발견된다. `ci.yml`을 작성해 PR 시 자동 검사 체계를 갖춘다.
Docker 스택: 개발 환경을 수동으로 구성해 환경 불일치가 잦다. `docker-compose.yml`로 AI 서버·백엔드·PostgreSQL·Chroma를 단일 명령으로 기동할 수 있게 한다.
성능 개선: 단일 의미 검색만 사용해 API 함수명 같은 키워드 기반 질의에서 recall이 낮다. BM25 + 의미 검색 하이브리드로 전환해 precision@3을 개선한다. 청킹 전략과 임베딩 모델은 변경하지 않는다.
ADR: Vector DB 선택(Chroma vs Weaviate)을 결정했으나 근거가 기록되어 있지 않아 나중에 이유를 추적할 수 없다. `docs/adr/0001-*.md`로 결정 근거를 문서화한다.
-->

- 여기에 작성

## ✅ 작업 내용

<!--
이번 이슈 범위에서 수행할 항목만 나열한다. 결과는 PR에 작성한다.

이 프로젝트 맥락 예시:
CI:
- `.github/workflows/ci.yml`에 `ruff check`·`ruff format`·`mypy`·`pytest` 단계를 추가합니다.
- `gitleaks` secret 스캔을 추가합니다.
- PR 제목·브랜치명·linked issue 체크를 추가합니다.
Docker 스택:
- `infra/docker-compose.yml`에 `postgres`·`chroma`·`ai-server`·`backend`·`frontend` 서비스를 정의합니다.
- `infra/docker-compose.override.yml`에 로컬 볼륨 마운트와 포트 노출을 분리합니다.
Python 환경:
- `ai-server/pyproject.toml`에 `FastAPI`·`langchain`·`langchain-openai`·`chromadb`·`rank_bm25` 의존성을 추가합니다.
- `uv lock`으로 lock 파일을 생성하고 커밋합니다.
테스트:
- `ai-server/tests/test_retrieval_filter.py`에 버전별 Chroma 메타데이터 필터 단위 테스트를 추가합니다.
- LLM 실제 호출 없이 mock으로 RAG 체인 응답 경로를 검증합니다.
-->

- 작업 항목 1
- 작업 항목 2

## 📊 측정 기준 (선택)

<!--
perf 이슈라면 필수. 그 외에는 섹션을 삭제한다.
"빨라진다", "좋아진다"는 완료 기준이 될 수 없다.
지표·현재값·목표값·측정 방법·평가셋 버전을 모두 적는다.

이 프로젝트 맥락 예시:
| 지표 | Before | After (목표) | 측정 방법 |
|---|---|---|---|
| precision@3 | 0.62 | 0.75 이상 | `qa_eval_v1.jsonl` 평가셋, top-3 검색 |
| faithfulness | 0.71 | 0.80 이상 | RAGAS, `gpt-4o-mini` 채점자, `qa_eval_v1.jsonl` |
| answer_relevance | 0.68 | 0.75 이상 | RAGAS, 동일 평가셋 |
-->

| 지표 | Before | After (목표) | 측정 방법 |
|---|---|---|---|
| (지표) | (현재값) | (목표값) | (측정 방법) |

## 🔗 연관 이슈 (선택)

<!-- 관련 이슈가 있을 때만 작성한다. 없으면 섹션 삭제. -->

- Related to #

## 🧭 우선순위

<!-- 하나만 체크한다. 체크 문구는 바꾸지 않는다. -->

- [ ] 🔴 Urgent — 지금 처리 안 하면 다른 작업이 막힘
- [ ] 🟠 High — MVP 핵심 기능 또는 일정에 직접 영향
- [ ] 🟡 Medium — 일반 기능 구현, 개선
- [ ] 🟢 Low — 후순위 정리, 문서, 단순 개선

## 📏 예상 작업 규모

<!-- 하나만 체크한다. -->

- [ ] 🔴 High — 2일 이상
- [ ] 🟠 Medium — 하루 내외
- [ ] 🟢 Low — 반나절 이내

## 📅 완료 기한

yyyy-mm-dd (요일)

## 📎 참고 자료 (선택)

<!-- 관련 문서, 공식 문서, 이전 측정 결과 링크. 없으면 섹션 삭제. -->

- 여기에 작성