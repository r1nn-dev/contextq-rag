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
