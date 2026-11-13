# RAG 평가 지표 및 방법론

> **최종 수정**: 2026-11-05

---

## 1. 개요

- **목적**: E1~E6 실험에서 사용하는 평가 메트릭을 정의하고, 결과 기록 스키마 및 판정 기준을 명시한다.
- **범위**: 검색 품질(E1·E2), 답변 정확도(E3), 성능(E5·E6)을 포함한다. 실험 절차 자체는 `claude/protocol.md`를, 질문셋 정의는 `claude/eval-scenarios.md`를 참조한다.
- **공통 조건**: seed=42, temperature=0, 모든 실험 결과는 `eval/results/{실험ID}/` 에 저장.

---

## 2. 메트릭 정의

### 2.1 검색 품질 메트릭 (E1·E2)

#### Hit@K

> 반환된 Top-K 청크 중 적어도 하나가 gold 섹션에 해당하면 1, 아니면 0.

```
Hit@K(q) = 1  if ∃ c ∈ Top-K(q) : c.heading_path ∈ gold_sections(q)
         = 0  otherwise

Hit@K = (1/|Q|) × Σ Hit@K(q)   for q ∈ Q
```

- `gold_sections(q)`: `eval/questions/{셋}/{ID}.yaml`의 `gold.sections`
- `heading_path` 비교: 대소문자 무시, 앞뒤 공백 제거 후 정확히 일치

#### MRR@K (Mean Reciprocal Rank)

> Top-K 결과 중 첫 번째 gold 청크의 역순위.

```
RR@K(q) = 1/rank_first_gold  if gold 청크가 Top-K 내 존재
         = 0                  otherwise

MRR@K = (1/|Q|) × Σ RR@K(q)
```

#### Precision@K

> Top-K 결과 중 올바른 소스의 gold 청크 비율. E2 청킹 전략 비교에서 버전 혼입 감도를 측정한다.

```
Precision@K(q) = |{c ∈ Top-K(q) : c.source_key == target_source_key(q) AND c 관련}| / K
```

- 소스 키는 `c.source_key` 필드로 판정한다 (예: `"langchain_v03"`, `"langchain_v1x"`).
- \"관련\"은 gold_sections 목록에 포함 여부로 판정한다.

#### 버전 혼입률 (E1 전용)

> Top-K 반환 청크 중 요청 소스와 다른 청크의 비율.

```
ContaminationRate@K(q) = |{c ∈ Top-K(q) : c.source_key ≠ target_source_key(q)}| / K

ContaminationRate@K = (1/|Q|) × Σ ContaminationRate@K(q)
```

- `target_source_key(q)`: 질문 `q`에 지정된 소스 키 (예: `"langchain_v03"`, `"langchain_v1x"`)

---

### 2.2 NO_CONTEXT 판정 메트릭 (E1 부속)

τ 최적화를 위해 Q-oos와 Q-ret 질문셋 모두에 대해 아래 지표를 측정한다.

| 메트릭 | 정의 | 목표 |
| --- | --- | --- |
| **Recall_NC** | Q-oos 중 NO_CONTEXT 반환 비율 | ≥ 0.90 |
| **FPR_NC** | Q-ret 중 NO_CONTEXT 오발동 비율 | ≤ 0.05 |
| **F1_NC** | 2 × (Recall_NC × (1−FPR_NC)) / (Recall_NC + (1−FPR_NC)) | 최대화 |

τ 결정 절차: `claude/protocol.md` §E1 참조.

---

### 2.3 답변 정확도 메트릭 (E3)

#### 버전 오류율 (Version Error Rate)

```
VER(condition) = |{(q,v) : label_version_error(q,v,condition) == 1}| / |Q_shared × V|
```

- `Q_shared`: 20문항, `V = {v0.3, v1.x}` → 총 40개 (q, v) 쌍
- `label_version_error`: 블라인드 레이블링 결과 (0 = 오류 없음, 1 = 오류)

#### Cohen's κ (레이블러 간 일치도)

서로 독립적으로 레이블링한 두 결과 사이의 일치도.

```
κ = (P_o - P_e) / (1 - P_e)
```

| κ 범위 | 해석 |
| --- | --- |
| < 0.20 | 무시할 수 있는 일치 |
| 0.20–0.40 | 낮은 일치 |
| 0.41–0.60 | 보통 일치 |
| 0.61–0.80 | 양호한 일치 |
| > 0.80 | 거의 완전한 일치 |

**κ ≥ 0.61 미만이면 레이블링 기준을 재협의하고 재레이블링한다.**

#### 근거 품질 (Evidence Quality, R1·R2 조건만)

```
EvidenceScore(condition) = mean(label_evidence_quality)   # 0=없음 / 1=부분 / 2=충분
```

---

### 2.4 성능 메트릭 (E5·E6)

#### TTFT (Time to First Token, E5)

> HTTP 요청 전송 완료부터 첫 번째 `token` SSE 이벤트 수신까지의 시간.

```
TTFT = t_first_token_event - t_request_sent
```

- **측정 위치**: 클라이언트 (curl 또는 k6 스크립트)
- **측정 횟수**: 20회 (10회 워밍업 제외 → 유효 10회)
- **보고 통계**: mean, p50, p95, min, max
- **목표**: p95 ≤ 3,000ms (EC2 t3.small)

#### Retriever 지연 (E5 부속)

```
RetrieverLatency = t_retrieve_done - t_embed_start   # 임베딩 + Chroma 검색 합산
```

- **측정 위치**: ai-server 내부 로그 (`retrieval_done.latency_ms`)
- **목표**: p95 ≤ 500ms

#### EmbeddingClient 지연 (E5 부속)

```
EmbeddingLatency = t_embed_done - t_embed_start
```

- **목표**: p95 ≤ 200ms

#### k6 부하 테스트 메트릭 (E6)

| 메트릭 | k6 변수명 | 목표 |
| --- | --- | --- |
| 에러율 | `http_req_failed` | ≤ 1% |
| 응답 시간 p95 | `http_req_duration{p(95)}` | ≤ 5,000ms |
| 동시 연결 수 | VU (virtual users) | 50 VU 도달 후 유지 |
| 처리량 | `http_reqs` | 측정값 기록 (목표 미지정) |

---

## 3. 결과 기록 스키마

### 3.1 E1 — 버전 격리 측정

파일: `eval/results/e1/e1_results.jsonl` (한 행 = 한 질문 × 한 조건)

```json
{
  "experiment_id": "e1",
  "run_date": "2026-11-15",
  "condition": "E1-C",
  "question_id": "RET-001",
  "version": "v1.x",
  "top_k": 5,
  "max_score": 0.78,
  "tau": 0.42,
  "no_context_triggered": false,
  "chunks_returned": [
    {"chunk_id": "agents_tools_0012", "source_key": "langchain_v1x", "similarity": 0.78, "is_gold": true},
    {"chunk_id": "agents_tools_0003", "source_key": "langchain_v1x", "similarity": 0.71, "is_gold": false}
  ],
  "hit_at_k": 1,
  "rr_at_k": 1.0,
  "contamination_at_k": 0.0
}
```

> **스키마 노트**: `chunks_returned[].source_key`는 Chroma 메타데이터 필드 (`"langchain_v03"` / `"langchain_v1x"`); `chunks_returned[].similarity`는 코사인 유사도 (0.0~1.0). 최상위 `version` 필드는 질문 타겟 버전 메타데이터 (`"v0.3"` / `"v1.x"`) — human-readable 분류용.

### 3.2 E2 — 청킹 전략 비교

파일: `eval/results/e2/e2_results.jsonl`

```json
{
  "experiment_id": "e2",
  "run_date": "2026-11-20",
  "strategy": "B",
  "question_id": "RET-007",
  "version": "v1.x",
  "top_k": 5,
  "hit_at_k": 1,
  "rr_at_k": 0.5,
  "precision_at_k": 0.4,
  "contamination_at_k": 0.0,
  "chunks_returned": [
    {"chunk_id": "...", "source_key": "langchain_v1x", "similarity": 0.72, "is_gold": true}
  ]
}
```

### 3.3 E3 — 답변 정확도 비교

파일: `eval/results/e3/e3_labels.jsonl` (레이블링 완료 후 최종본)

```json
{
  "experiment_id": "e3",
  "run_date": "2026-11-25",
  "condition": "L0",
  "question_id": "SHR-001",
  "version": "v0.3",
  "answer_text": "LangChain v0.3에서 에이전트를 생성하려면 AgentExecutor를 ...",
  "sources_returned": ["Agents > AgentExecutor", "Agents > create_react_agent"],
  "label_version_error": 0,
  "label_evidence_quality": null,
  "label_usefulness": 2,
  "labeler": "r1nn-dev",
  "labeler_b": "external",
  "kappa_pair": 0.74
}
```

### 3.4 E5 — TTFT 성능

파일: `eval/results/e5/e5_ttft.jsonl`

```json
{
  "experiment_id": "e5",
  "run_date": "2026-11-28",
  "environment": "ec2-t3-small",
  "trial": 11,
  "is_warmup": false,
  "version": "v0.3",
  "question_id": "RET-003",
  "ttft_ms": 1842,
  "retriever_latency_ms": 312,
  "embed_latency_ms": 187,
  "prompt_tokens": 1204,
  "completion_tokens": 183
}
```

### 3.5 E6 — k6 부하 테스트

k6 내장 출력으로 JSON 요약 저장. 추가 필드:

```json
{
  "experiment_id": "e6",
  "run_date": "2026-11-30",
  "scenario": "S2",
  "max_vus": 50,
  "duration_sec": 300,
  "mock_llm": true,
  "http_req_failed_pct": 0.3,
  "http_req_duration_p95_ms": 2410,
  "http_reqs_total": 4821
}
```

---

## 4. 집계 스크립트

| 스크립트 | 입력 | 출력 |
| --- | --- | --- |
| `scripts/eval/aggregate_e1.py` | `eval/results/e1/e1_results.jsonl` | `eval/results/e1/e1_summary.json` (조건별 Hit@K, MRR@K, ContamRate 평균) |
| `scripts/eval/aggregate_e2.py` | `eval/results/e2/e2_results.jsonl` | `eval/results/e2/e2_summary.json` (전략별 메트릭 비교표) |
| `scripts/eval/aggregate_e3.py` | `eval/results/e3/e3_labels.jsonl` | `eval/results/e3/e3_summary.json` (조건별 VER, κ, EvidenceScore) |
| `scripts/eval/aggregate_e5.py` | `eval/results/e5/e5_ttft.jsonl` | `eval/results/e5/e5_summary.json` (mean, p50, p95, min, max) |

**공통 옵션:**
```bash
python scripts/eval/aggregate_e1.py \
    --input eval/results/e1/e1_results.jsonl \
    --output eval/results/e1/e1_summary.json
```

---

## 5. 보고 기준

### 5.1 합격 임계값

| 실험 | 메트릭 | 합격 기준 |
| --- | --- | --- |
| E1 | ContaminationRate@5 (E1-C) | ≤ 0.00 (컬렉션 분리 조건에서 혼입 0건) |
| E1 | Recall_NC | ≥ 0.90 |
| E1 | FPR_NC | ≤ 0.05 |
| E2 | Hit@5 (채택 전략) | ≥ 0.70 |
| E2 | MRR@5 (채택 전략) | ≥ 0.60 |
| E3 | VER (L1·R1 대비 L0) | L0 VER ≥ L1·R1 (격리 효과 입증) |
| E3 | Cohen's κ | ≥ 0.61 |
| E5 | TTFT p95 | ≤ 3,000ms |
| E5 | RetrieverLatency p95 | ≤ 500ms |
| E6 | 에러율 | ≤ 1% |

### 5.2 판정 규칙

- 임계값을 충족하지 못한 실험은 **재실험 또는 설계 재검토** 대상이다.
- E2에서 어떤 전략도 Hit@5 ≥ 0.70을 충족하지 못하면 `eval/decision_rules.md`에 사유를 기록하고 k 또는 τ 조정을 검토한다.
- E3에서 κ < 0.61이면 레이블링 기준을 재협의하고 `eval/decision_rules.md`에 변경 사항을 기록한 뒤 재레이블링한다.

### 5.3 보고서 포함 항목

보고서(`docs/report.md`) 실험 절에 포함해야 하는 최소 항목:

```
- 실험 조건 및 질문셋 커밋 해시
- 사용 모델·파라미터 (seed, temperature, top_k, τ)
- 메트릭 결과표 (mean ± std 또는 p50/p95)
- 합격 기준 충족 여부
- 이상치·예외 케이스 설명
- 채택 결정 및 근거 (E2 청킹 전략, E1 τ 값)
```

---

## 미결 사항

- [ ] **EV-1** E3 외부 레이블러 섭외 및 레이블링 가이드 작성 (W4 이전)
- [ ] **EV-2** `scripts/eval/aggregate_*.py` 구현 (E1 실험 1주일 전까지)
- [ ] **EV-3** E6 k6 시나리오 S0~S4 스크립트 작성 (`scripts/load/`) — `claude/protocol.md` §E6 참조
- [ ] **EV-4** TTFT 측정 위치 확정 — 클라이언트 측(curl) vs 서버 로그 중 primary로 사용할 기준 결정
- [ ] **EV-5** Cohen's κ 계산 스크립트 (`scripts/eval/kappa.py`) 구현

---

## 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | Precision@K / 버전 혼입률 수식의 `c.version` → `c.source_key` 통일; E1 결과 JSONL의 `chunks_returned.version` → `source_key` |

---

*end.*
