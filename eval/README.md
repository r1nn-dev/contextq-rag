# eval — RAG 평가 질문셋·결정 규칙·결과

실험 E1~E3의 입력과 산출물을 둔다. 실험 절차는 `docs/experiments/protocol.md`, 지표 정의는 `docs/experiments/evaluation.md`, 질문셋 규칙은 `docs/experiments/eval-scenarios.md`를 따른다.

## 구조

```
eval/
  questions/
    RET/RET-001.yaml …   # Q-ret 40개 — 검색 품질·혼입 (E1·E2)
    OOS/OOS-001.yaml …   # Q-oos 10개 — NO_CONTEXT (E1 부속)
    SHR/SHR-001.yaml …   # Q-shared 20개 × 2버전 — 답변 버전 정확도 (E3)
  decision_rules.md      # E2 사전 결정 규칙 (eval-v1 태그 이전 커밋, 불변)
  rubric.md              # E3 블라인드 레이블링 루브릭
  results/               # 실험 결과 (실험별 하위 디렉터리)
  cache/                 # LLM 응답 캐시 (커밋하지 않음)
```

## 질문셋 규칙 요약

- 질문 1개 = YAML 파일 1개. 파일명 = `question_id` (`{RET|OOS|SHR}-3자리 숫자`).
- gold는 `{file_path, heading_path}` 쌍이고 `heading_path` 깊이는 2 이하(`페이지 제목 > H2`)다. 청크가 같은 파일이면서 gold 섹션이거나 그 하위 섹션이면 적중이다.
- gold는 ACTIVE 인덱스에 있는 섹션만 쓴다. `integrations/**`·`langgraph` 문서는 gold로 쓰지 않는다(정책서 §3.2).
- AI가 초안을 쓰고 사람이 검수한다. 검수자는 `metadata.reviewed_by`를 채운다.
- 모든 문항의 `reviewed_by`가 채워진 커밋에 `eval-v1` 태그를 단다. 태그 이후 질문셋을 바꾸면 그 실험 결과는 `contaminated`로 표시하고 보고에서 뺀다.

## 검증

질문셋 스키마와 v1 구성(셋별 문항 수, Q-ret 버전·디코이 배분)은 단위 테스트가 검사한다.

```bash
cd ai-server
uv run pytest -q tests/unit/test_eval_questions.py
```

## 실행

```bash
make eval-check                          # 질문셋 검증 (비밀값 불필요)
make eval EXP=E1 CONDITIONS="N F"        # E1 비격리·필터 조건 → eval/results/E1/
make eval                                # E1(N·F·C)·E2 — 서비스 Retriever(R-4-1)·전략별 인덱스(R-7-3) 연결 후
```

- DB(ACTIVE 포인터)·Chroma 인덱스·OpenAI 키(질의 임베딩)가 필요하므로 별도 터미널에서 실행한다.
- 출력: `{실험}/e{n}_results.jsonl`(질문 × 조건 × 버전 × K 한 행), `{실험}/e{n}_summary.csv`, `{실험}/env.txt`.
