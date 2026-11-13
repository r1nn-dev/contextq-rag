# docs/

ContextQ-RAG 프로젝트 설계·실험·운영 문서 디렉토리.

## 디렉토리 구조

| 디렉토리 | 용도 |
|---|---|
| `adr/` | 아키텍처 의사결정 기록 (Architecture Decision Records) |
| `specs/` | 시스템 설계·API·인터페이스 명세 |
| `experiments/` | RAG 평가 프로토콜·시나리오·결과 |
| `planning/` | 기획서·정책·로드맵 |
| `architecture/` | 시스템 아키텍처 다이어그램·DB 설계 |
| `ops/` | 배포 환경 구성·운영 절차 |
| `ui/` | UI 목업 HTML · 화면 스크린샷 |

## 작성 규칙

- API 계약 변경 시 반드시 `specs/` 반영 후 PR 셀프 체크리스트 체크.
- 아키텍처 결정 시 `adr/ADR-{번호}-{제목}.md` 작성 후 `Accepted` 상태로 머지.
- 실험 결과는 `experiments/results/`에 JSONL로 보관 (git 추적).