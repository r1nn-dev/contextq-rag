# ADR-011: EC2 단일 인스턴스 수직 확장 전략

## Status
Draft

## Date
2026-11-14 (2026-11-18 개정: 인스턴스 사양·볼륨 구성을 기획서 결정 6·운영 Compose 기준으로 정리)

## Context

인프라 확장 전략 결정:

- **수평 확장(Horizontal Scaling)**: 다수 EC2 인스턴스 + Load Balancer
  - Chroma 임베디드 모드는 단일 프로세스 접근만 허용 → 공유 불가
  - EFS 마운트로 Chroma 디렉토리 공유 가능하나 NFS latency 증가
  - 멀티 인스턴스 세션 동기화 문제 (Spring Boot stateful session)
- **수직 확장(Vertical Scaling)**: 단일 EC2 인스턴스 스펙 업
  - Chroma 임베디드 모드와 자연스럽게 호환
  - 운영 복잡도 최소화 — 개인 개발자 운영에 적합
  - 졸업작품 규모(소규모 동시 접속)에서 충분

## Decision

**EC2 단일 인스턴스, EBS 기반 Chroma 퍼시스턴트 볼륨, 수직 확장 우선** 전략을 채택한다.

**인스턴스 사양**:
| 항목 | 사양 |
|------|------|
| 인스턴스 타입 | `t3.small` (기본, 크레딧 사양 standard) → `c7i-flex.large` (부하 테스트·최종 시연 기간 일시 증설) |
| vCPU | 2 → 2 |
| RAM | 2 GiB → 4 GiB |
| 스토리지 | EBS gp3 20 GiB (Chroma + PostgreSQL + 로그, 사용률 ≤ 70%) |

근거: 기획서 결정 6(AWS 무료 플랜, `t3.small`)·부록 A 메모리 예산, 정책서 §11 "EBS 20GiB". 초안의 `t3.medium`·30GB는 무료 플랜 예산과 맞지 않아 2026-11-18에 고쳤다.

**Chroma 볼륨 구성**:
```yaml
# infra/docker-compose.yml — 루트 EBS 볼륨의 Docker 볼륨에 둔다 (별도 EBS 마운트 없음)
services:
  ai-server:
    volumes:
      - chroma_data:/app/chroma_db

volumes:
  chroma_data:
```

인덱스는 스냅샷 복원으로 채우고(ADR-005), 볼륨이 사라지면 같은 스냅샷을 다시 복원한다.

**수직 확장 트리거**:
- CPU 평균 > 70% (5분 지속)
- 메모리 사용률 > 80%
- 응답 P95 latency > 5s

확장 절차: EC2 콘솔 → 인스턴스 타입 변경 → 재시작 (다운타임 ~2분 허용)

**수평 확장 전환 조건** (졸업작품 이후 고려):
- 동시 접속 > 50명 지속
- 단일 인스턴스 최대 스펙(`t3.2xlarge`)으로도 부족
- 전환 시 Chroma → 클라이언트-서버 모드(`chromadb.HttpClient`) 전환 필요 (ADR-002 참조)

## Consequences

**장점**
- Chroma 임베디드 모드와 완전 호환 (ADR-002와 일관성)
- 운영 복잡도 최소 — 개인 개발자 단독 운영 가능
- 비용 최소화 (Load Balancer, Auto Scaling Group 불필요)

**단점 / 트레이드오프**
- 단일 장애점(SPOF) — 인스턴스 장애 시 전체 서비스 중단
- 수직 확장 한계 존재 (`t3.2xlarge`까지)
- 고트래픽 대응 한계 명확 — 졸업작품 규모에서는 비문제

**졸업작품 평가 맥락**
- "왜 수직 확장인가?" → Chroma 임베디드 설계(ADR-002)와 일관된 선택
- "수평 확장으로 가면?" → ADR-002의 클라이언트-서버 모드 전환으로 가능, 현 단계에서 복잡도 대비 이득 없음
- 이 결정은 기술적 타당성과 운영 현실성의 명시적 트레이드오프

**관련 ADR**
- ADR-002: Chroma 임베디드 모드 (수평 확장 제약의 근본 원인)
