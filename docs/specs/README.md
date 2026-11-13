# 명세 (specs/)

이 디렉토리에는 시스템 설계·API·인터페이스 명세를 보관한다.

| 파일 | 내용 |
|---|---|
| `sdd.md` | 소프트웨어 설계 명세 (Software Design Document) |
| `interfaces.md` | 서비스 간 인터페이스 계약 (내부 API, SSE 형식) |
| `rag-pipeline.md` | RAG 파이프라인 단계별 설계 |
| `test-plan.md` | 테스트 전략·레벨·커버리지 계획 |
| `data-sources.md` | 문서 소스 데이터·버전 명세 |
| `doc-source.md` | 문서 수집 대상·형식·파싱 전략 |
| `api-spec.md` | REST API 전체 명세 |

## 규칙

- API 계약 변경 시 `interfaces.md` 또는 `api-spec.md` 반영 필수.
- PR 셀프 체크리스트 "계약 변경 `docs/specs/` 문서 반영" 항목 체크.