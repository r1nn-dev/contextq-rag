# ADR-001: Spring Boot + FastAPI 이중 서버 구조

## Status
Draft

## Date
2026-11-14

## Context

ContextQ-RAG는 두 가지 성격이 다른 책임을 갖는다.

1. **웹 애플리케이션 로직**: 사용자 인증(JWT), 세션 관리, 대화 이력 저장(PostgreSQL), 게스트 쿼터 제한, REST API 제공
2. **ML/RAG 파이프라인**: 텍스트 임베딩(OpenAI API), Chroma 벡터 검색, LLM 호출(GPT-4o-mini), SSE 스트리밍, 질의 재작성

이 두 책임을 하나의 서버에서 처리하는 옵션도 고려했다:
- **옵션 A**: FastAPI 단일 서버 (Python으로 모든 것 처리)
- **옵션 B**: Spring Boot 단일 서버 (JVM에서 Python ML 라이브러리 연동)
- **옵션 C**: Spring Boot(웹/인증) + FastAPI(RAG 파이프라인) 이중 서버

## Decision

**옵션 C — Spring Boot + FastAPI 이중 서버 구조**를 채택한다.

- Spring Boot 4.1.2 (Java 21): 인증·세션·대화 이력·쿼터·REST API
- FastAPI (Python 3.11): 임베딩·Chroma 검색·LLM 호출·SSE 스트리밍

서버 간 통신은 HTTP REST (`INTERNAL_TOKEN` 헤더 인증). 외부에는 Spring Boot만 노출.

```
Frontend → Spring Boot (8080) → FastAPI (8001)
                               ↕
                           Chroma (embedded)
                           PostgreSQL (5432)
```

## Consequences

**장점**
- Python 생태계(LangChain, Chroma, tiktoken)를 FastAPI에서 그대로 사용 가능
- Spring Boot의 성숙한 보안 기능(Spring Security, JWT) 활용
- 각 서버 독립 배포·확장 가능

**단점 / 트레이드오프**
- 서버 2개 운영 — docker-compose 서비스 추가, 로컬 세팅 복잡도 증가
- 서비스 간 네트워크 호출 레이턴시 (내부망이므로 ~1ms 수준)
- `INTERNAL_TOKEN` 환경 변수 관리 필요

**관련 ADR**
- ADR-003: SSE 스트리밍 방식 (FastAPI → Spring Boot → Frontend 중계 vs. FastAPI 직접)
