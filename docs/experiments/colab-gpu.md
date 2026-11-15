# Colab GPU 실험 환경 가이드

> **최종 수정일:** 2026-11-15

Google Colab GPU 환경에서 RAG 평가·청킹 실험을 실행하는 방법을 정리한다.

---

## 1. 사전 조건

- Google Colab Pro / Pro+ 권장 (A100 또는 L4 GPU)
- OpenAI API 키 (평가 중 임베딩 호출 발생)
- GitHub 저장소 접근 권한

---

## 2. 환경 설정

### 2.1 저장소 클론

```python
# Colab 셀 1
!git clone https://github.com/r1nn-dev/contextq-rag.git /content/contextq-rag
%cd /content/contextq-rag
!git log --oneline -3   # 최신 커밋 확인
```

### 2.2 의존성 설치

```python
# Colab 셀 2 — uv 설치 후 dev 그룹 동기화
!pip install uv --quiet
!cd /content/contextq-rag/ai-server && uv sync --group dev
```

> Colab은 `uv`가 기본 미설치다. `pip install uv` 후 `uv sync --group dev`로 dev 의존성(pytest, ruff, mypy 등)을 포함해 설치한다.  
> `--extra eval` 옵션은 없다 — eval 테스트는 `dev` 그룹에 포함된다.

### 2.3 환경 변수 설정

**방법 A — Colab Secrets 사용 (권장)**

```python
from google.colab import userdata
import os

os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")
os.environ["CHROMA_DATA_DIR"] = "/content/contextq-rag/data/chroma"
```

> Colab Secrets 등록: 왼쪽 사이드바 🔑 아이콘 → `OPENAI_API_KEY` 추가

**방법 B — 직접 설정**

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-..."        # 노트북에 하드코딩 금지
os.environ["CHROMA_DATA_DIR"] = "/content/contextq-rag/data/chroma"
```

> **주의:** 노트북에 API 키를 직접 넣지 않는다. 커밋 시 노출 위험.

### 2.4 Chroma 데이터 디렉터리 생성

```python
!mkdir -p /content/contextq-rag/data/chroma
```

---

## 3. RAG 평가 실행

### 3.1 pytest eval 마커 실행

```python
%cd /content/contextq-rag/ai-server

# eval 마커만 실행 (OpenAI API 호출·비용 발생)
!uv run pytest -m eval -q --tb=short
```

### 3.2 E2 평가 스크립트 직접 실행

```python
!uv run python /content/contextq-rag/scripts/eval/run_e2.py
```

> 스크립트 위치: `scripts/eval/run_e2.py`  
> 평가 질문셋: `eval/questions/`  
> 결과 저장: `eval/results/e2/`

---

## 4. 청킹 실험

```python
# 청킹 전략 비교 실험 예시
!uv run python /content/contextq-rag/scripts/eval/chunking_experiment.py

# 결과 노트북으로 분석
# 완료 후 노트북을 eval/notebooks/에 저장
```

Colab에서 작업한 노트북(`.ipynb`)은 반드시 `eval/notebooks/`에 저장 후 커밋한다.

---

## 5. 결과 저장 및 커밋

### 5.1 디렉터리 구조

```
eval/
├── questions/           # 평가 질문셋 (버전 관리)
├── results/
│   └── e2/              # E2 평가 결과 JSON
└── notebooks/           # 실험 노트북 (.ipynb)
```

### 5.2 결과 커밋

```bash
# 평가 결과
git add eval/results/e2/
git commit -m "chore(eval): <실험명> E2 평가 결과 추가 (날짜)"

# 실험 노트북
git add eval/notebooks/<notebook_name>.ipynb
git commit -m "chore(eval): <실험명> 청킹 실험 노트북 추가"
```

> 결과 파일명에 날짜(`YYYY-MM-DD`)를 포함해 추적성을 확보한다.

---

## 6. Google Drive 백업 (선택)

Colab 세션 종료 시 `/content/` 하위 파일이 소실된다. 장시간 실험은 Drive에 백업한다.

```python
from google.colab import drive
drive.mount('/content/drive')

import shutil
shutil.copy(
    '/content/contextq-rag/eval/results/e2/result_2026-11-14.json',
    '/content/drive/MyDrive/contextq-rag/eval/'
)
```

---

## 7. 향후 활용: 커스텀 청커 실험

ai-server 청킹 로직 (`ai-server/src/ingest/pipeline.py`) 변경 없이 Colab에서 프로토타입을 먼저 검증하고, 결과가 좋으면 `pipeline.py`에 반영하는 흐름을 따른다.

```python
# Colab에서 프로토타입 실험
import sys
sys.path.insert(0, '/content/contextq-rag/ai-server')

from src.ingest import pipeline   # src/ 레이아웃 임포트

# 커스텀 청커 함수 정의 후 비교
def semantic_chunker(text, ...): ...
```

---

## 8. 주의사항

| 항목 | 내용 |
|---|---|
| 비용 | 평가 실행 시 OpenAI API 호출 비용 발생 |
| 세션 소실 | Colab 세션 종료 시 `/content/` 삭제 → Drive 백업 필수 |
| `CHROMA_DATA_DIR` | 절대 경로 필수 (`/content/contextq-rag/data/chroma`) |
| `CHROMA_PORT` | **사용하지 않음** — Chroma는 임베디드 (별도 포트 없음) |
| 노트북 커밋 | 실험 결과 노트북은 `eval/notebooks/`에 커밋해 재현성 확보 |
| 임포트 경로 | `from src.ingest import ...` (`from ai_server.ingest` 아님) |
