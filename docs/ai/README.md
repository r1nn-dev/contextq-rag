# AI 협업 가이드

ContextQ-RAG 저장소에서 AI 도구(Claude Code, Gemini 등)와 협업하는 방법을 안내합니다.

## 파일 목록

| 파일 | 설명 |
|---|---|
| `AGENTS.md` (저장소 루트) | AI 공통 규칙 (English, 포인터 방식) |
| `CLAUDE.md` (저장소 루트) | Claude Code CLI 전용 임포트 (`@AGENTS.md`) |
| `docs/ai/prompts/` | 단계별 프롬프트 파이프라인 |
| `docs/ai/review-checklist.md` | 코드 리뷰 체크리스트 |

## 프롬프트 파이프라인

| 파일 | 단계 | 용도 |
|---|---|---|
| `00-session-start.md` | 세션 시작 | 컨텍스트 로딩 |
| `10-plan.md` | 계획 | 작업 계획 수립 |
| `20-issue-write.md` | 이슈 작성 | GitHub 이슈 초안 |
| `30-implement.md` | 구현 | 코드 구현 |
| `40-review.md` | 리뷰 | 코드 리뷰 |
| `50-pr-write.md` | PR 작성 | Pull Request 초안 |
| `60-troubleshoot.md` | 트러블슈팅 | 에러 디버깅 |

> 프롬프트 파이프라인 파일은 별도 이슈에서 작성 예정.