# 사전 결정 규칙 (eval-v1)

> **성격:** 실험 결과를 보기 전에 채택 기준을 고정한다. 이 파일은 `eval-v1` 태그 이전에 커밋하며, 태그 이후에는 바꾸지 않는다.
> **작성:** 기준 문서에 이미 확정된 규칙을 문구 그대로 옮겼다. 새 판단은 넣지 않았고, 문서에 없어 해석이 필요한 부분은 "사람 확인 필요"로 따로 표시했다.
> **근거:** `docs/experiments/protocol.md` 실험 E2 사전 결정 규칙 · `docs/planning/policy.md` §5.3 · 미결정 사항 표 · `docs/experiments/evaluation.md` §5

---

## 1. E2 — 청킹 전략 채택

| 순서 | 규칙 | 근거 |
| --- | --- | --- |
| 1 | **기본 채택 기준:** Q-ret 40문항 Hit@5가 가장 높은 전략을 채택한다. | `protocol.md` > 실험 E2 > 사전 결정 규칙 1 |
| 2 | **동률 처리:** 1·2위 Hit@5 차이가 3%p 미만이면 평균 컨텍스트 토큰이 더 적은 전략을 채택한다. | `protocol.md` > 실험 E2 > 사전 결정 규칙 2 · `policy.md` > 미결정 사항 > 청킹 전략 |
| — | 규칙 적용 순서는 1 → 2 → (§2 K 결정)이며, 커밋 이후 변경하지 않는다. | `protocol.md` > 실험 E2 > 사전 결정 규칙 4 |

- 비교 전략: A(CharacterTextSplitter) · B(RecursiveCharacterTextSplitter) · C(구조 인식). 파라미터는 `ai-server/configs/ingest.yaml`의 값 그대로다.
- 평균 컨텍스트 토큰: Top-5 청크 `token_count`의 평균(`protocol.md` > 실험 E2 > 지표).
- 블라인드: gold 레이블링(질문셋 v1)을 먼저 끝내고 그 뒤에 전략별 점수를 계산한다(`protocol.md` > 실험 E2 > 블라인드 절차).
- 합격 기준: 채택 전략 Hit@5 ≥ 0.70, MRR@5 ≥ 0.60(`evaluation.md` §5.1). 어떤 전략도 Hit@5 ≥ 0.70을 넘지 못하면 이 파일 §5에 사유를 기록하고 K 또는 τ 조정을 검토한다(`evaluation.md` §5.2).

## 2. E2 — 운영 Top-K 결정

| 규칙 | 근거 |
| --- | --- |
| 채택 전략에서 K ∈ {3, 5, 8} 중 **Hit@K 증가폭이 2%p 미만이 되는 최소 K**를 운영 Top-K로 쓴다. | `protocol.md` > 실험 E2 > 사전 결정 규칙 3 · `policy.md` > §5.3 Top-K · 미결정 사항 > Top-K |

- 결정 결과는 `eval/results/E2/decision.md`에 기록한다(`protocol.md` > 실험 E2 > 산출물).

## 3. E1 부속 — NO_CONTEXT 임계값 τ 결정

| 순서 | 절차 | 근거 |
| --- | --- | --- |
| 1 | Q-ret 40문항을 두 버전 컬렉션에서 각각 검색해 최대 유사도 분포를 기록한다(80회). | `protocol.md` > 실험 E1 > τ 결정 절차 1 |
| 2 | Q-oos 10문항을 두 버전 컬렉션에서 각각 검색해 최대 유사도 분포를 기록한다(20회). | `protocol.md` > 실험 E1 > τ 결정 절차 2 |
| 3 | τ는 Q-ret 최소값과 Q-oos 최대값 사이에서 오탐(범위 안 질문이 NO_CONTEXT)과 미탐(범위 밖 질문이 통과)의 균형점으로 정한다. 균형점은 F1_NC 최대화로 판정한다. | `protocol.md` > 실험 E1 > τ 결정 절차 3 · `evaluation.md` §2.2 F1_NC "최대화" · `policy.md` > 미결정 사항 > NO_CONTEXT 임계값 τ |
| 4 | τ는 source_key별로 정한다(`langchain_v03`, `langchain_v1x` 각각). | `docs/adr/ADR-008-no-context.md` > Decision "source_key별 개별값" |
| 5 | 정한 τ를 이 파일 §5와 운영 설정에 반영하고, 인덱스 검증 스모크 기준도 같은 τ로 다시 실행한다. | `protocol.md` > 실험 E1 > τ 결정 절차 4 · `policy.md` > 미결정 사항 > NO_CONTEXT 임계값 τ |

- 지표 정의: Recall_NC = Q-oos 중 NO_CONTEXT 비율, FPR_NC = Q-ret 중 NO_CONTEXT 오발동 비율, F1_NC = 2 × (Recall_NC × (1 − FPR_NC)) / (Recall_NC + (1 − FPR_NC)) (`evaluation.md` §2.2).
- 합격 기준: Recall_NC ≥ 0.90, FPR_NC ≤ 0.05 (`evaluation.md` §5.1).

## 4. 컨텍스트 토큰 예산

| 규칙 | 근거 |
| --- | --- |
| E2 확정 후 `min(3000, K_final × avg_chunk_tokens × 1.15)`를 적용한다. 상한 3,000은 고정이고 실제 예산은 낮아질 수 있다. | `policy.md` > 미결정 사항 > 컨텍스트 토큰 예산 |
| 예산을 넘으면 낮은 rank 청크부터 뺀다. 청크 중간을 자르지 않는다. | `policy.md` > §5.3 컨텍스트 예산 |

## 5. 결정 기록

> 실험 후 결과만 채운다. 위 규칙은 바꾸지 않는다.

| 항목 | 결정값 | 근거 결과 파일 | 날짜 |
| --- | --- | --- | --- |
| 채택 청킹 전략 |  | `eval/results/E2/` |  |
| 운영 Top-K |  | `eval/results/E2/` |  |
| τ (`langchain_v03`) |  | `eval/results/E1/` |  |
| τ (`langchain_v1x`) |  | `eval/results/E1/` |  |
| 컨텍스트 토큰 예산 |  | §4 공식 |  |

## 6. 사람 확인 필요 (`eval-v1` 태그 전)

기준 문서만으로는 한 가지로 읽히지 않는 부분이다. 태그 전에 사람이 정하고 이 표를 지운 뒤 위 규칙에 반영한다.

| # | 항목 | 해석이 갈리는 지점 | 초안의 읽기 (참고용) |
| --- | --- | --- | --- |
| 1 | K 규칙의 "증가폭" | 어느 K와 어느 K 사이의 증가폭인지 문서에 없다 | K=3→5, 5→8 순서로 보고 `Hit@다음K − Hit@K < 2%p`인 첫 K. 끝까지 없으면 8 |
| 2 | 동률 처리 기준값 | 3%p 미만을 "Hit@5 비율 차이(퍼센트포인트)"로 본다 | Hit@5를 백분율로 바꾼 차이 |
| 3 | τ 동점 처리 | F1_NC 최대값이 여러 τ에서 같을 때 고를 값이 문서에 없다 | — (사람 결정) |
| 4 | τ 후보 범위 | Q-ret 최소값 > Q-oos 최대값이면 구간이 비지 않지만, 반대로 겹치면 "사이"가 정의되지 않는다 | 겹치면 두 분포 전체 범위에서 F1_NC 최대화 |
| 5 | NO_CONTEXT 처리율 목표 | `protocol.md` > 실험 E1 > 지표는 "Q-oos 10개 중 8건 이상(80%)", `evaluation.md` §5.1은 Recall_NC ≥ 0.90 | — (사람 결정, 다른 쪽 문서 정정 필요) |
| 6 | `avg_chunk_tokens` | 채택 전략 컬렉션 전체 청크 평균인지, E2 Top-K 반환 청크 평균인지 문서에 없다 | — (사람 결정) |
