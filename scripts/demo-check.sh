#!/usr/bin/env bash
# 시연 전 상태 점검 — 로컬 시연 스택(`make up`)이 시연 가능한지 1분 안에 판정한다.
#
#   scripts/demo-check.sh            # 전체 점검 (게스트 질문 1회 = OpenAI 호출 1회)
#   scripts/demo-check.sh --no-llm   # 질문 생략 (OpenAI 호출 없음)
#
# 점검 항목: 컨테이너 4개 healthy → ai-server 헬스(Chroma·DB·소스별 ACTIVE run)
# → nginx 경유 소스 목록 → nginx 경유 게스트 질문(meta → token → done COMPLETED, 첫 토큰 시간)
# → ACTIVE run 인덱스 스냅샷 백업(없으면 경고만).
# 종료 코드: 0 = 실패 없음(경고 허용), 1 = 실패 1건 이상, 2 = 사용법 오류.
#
# 로컬 오버레이 전용이다(ai-server 8000 포트를 직접 부른다). 환경 파일은 읽지 않는다(비밀값).
# 주소·질문은 환경 변수로 바꾼다: DEMO_CHECK_BASE_URL, DEMO_CHECK_AI_HEALTH_URL,
# DEMO_CHECK_SOURCE, DEMO_CHECK_QUESTION, DEMO_CHECK_MIN_SOURCES, DEMO_CHECK_SNAPSHOT_DIR.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE_URL="${DEMO_CHECK_BASE_URL:-http://localhost:${NGINX_HTTP_PORT:-80}}"
AI_HEALTH_URL="${DEMO_CHECK_AI_HEALTH_URL:-http://localhost:${AI_SERVER_PORT:-8000}/internal/v1/health}"
SOURCE_KEY="${DEMO_CHECK_SOURCE:-langchain_v1x}"
QUESTION="${DEMO_CHECK_QUESTION:-How do I create an agent?}"
MIN_SOURCES="${DEMO_CHECK_MIN_SOURCES:-2}"
SNAPSHOT_DIR="${DEMO_CHECK_SNAPSHOT_DIR:-$REPO_ROOT/ai-server/data/snapshots}"
SERVICES=(nginx backend ai-server postgres)
LOGS="docker compose -p contextq logs --tail 50"

RUN_LLM=1
case "${1:-}" in
  "") ;;
  --no-llm) RUN_LLM=0 ;;
  -h | --help)
    sed -n '2,5p' "$0"
    exit 0
    ;;
  *)
    sed -n '2,5p' "$0" >&2
    exit 2
    ;;
esac

FAILS=0
WARNS=0
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ok() { printf '[OK]   %s\n' "$1"; }
warn() {
  printf '[WARN] %s\n       조치: %s\n' "$1" "$2"
  WARNS=$((WARNS + 1))
}
fail() {
  printf '[FAIL] %s\n       조치: %s\n' "$1" "$2"
  FAILS=$((FAILS + 1))
}
skip() { printf '[SKIP] %s\n' "$1"; }

# 밀리초 단위 현재 시각 — bc가 없는 Git Bash에서도 되도록 EPOCHREALTIME을 정수로 바꾼다
now_ms() {
  local t="${EPOCHREALTIME/[.,]/}"
  echo $((t / 1000))
}

# 압축 JSON에서 문자열·숫자·불리언 필드 값을 꺼낸다(첫 번째 일치). 응답 형식이 계약으로 고정돼 있어 jq 없이 쓴다
json_field() {
  local key="$1" body="$2"
  printf '%s' "$body" | grep -o "\"$key\":\"\{0,1\}[^\",}]*" | head -n1 | sed "s/^\"$key\":\"\{0,1\}//"
}

START_MS="$(now_ms)"
echo "시연 전 점검 — $(date '+%F %T') · $BASE_URL"

# 1. 컨테이너 — Compose 프로젝트 이름(contextq)만으로 조회하므로 Compose·환경 파일이 필요 없다
check_containers() {
  local ps_out service line state health bad=""
  if ! ps_out="$(docker compose -p contextq ps -a --format '{{.Service}} {{.State}} {{.Health}}' 2>&1)"; then
    fail "컨테이너 — docker compose를 실행할 수 없음 (${ps_out%%$'\n'*})" "Docker Desktop 실행 확인 후 make up"
    return
  fi
  for service in "${SERVICES[@]}"; do
    line="$(printf '%s\n' "$ps_out" | grep -m1 "^$service " || true)"
    state="$(echo "$line" | cut -d' ' -f2)"
    health="$(echo "$line" | cut -d' ' -f3)"
    [ "$state" = "running" ] && [ "$health" = "healthy" ] || bad="$bad $service(${state:-없음}${health:+/$health})"
  done
  if [ -z "$bad" ]; then
    ok "컨테이너 ${#SERVICES[@]}개 healthy"
  else
    fail "컨테이너 —$bad" "make up 으로 재기동, 계속 실패하면 $LOGS <서비스>"
  fi
}

# 2. ai-server 헬스 — Chroma 로드·DB 연결·소스별 ACTIVE run (API 명세 §6.2, 토큰 없이 호출)
ACTIVE_RUNS=""
check_ai_health() {
  local code body inactive="" pair run
  code="$(curl -s -o "$TMP_DIR/health.json" -w '%{http_code}' --max-time 5 "$AI_HEALTH_URL")" || code="000"
  body="$(cat "$TMP_DIR/health.json" 2>/dev/null | tr -d ' \r\n')"
  if [ "$code" = "000" ]; then
    fail "ai-server 헬스 — 연결 실패 ($AI_HEALTH_URL)" "$LOGS ai-server"
    return
  fi
  # "langchain_v03":{"activeRun":true,"ingestRunId":6} 형태의 소스별 항목
  for pair in $(printf '%s' "$body" | grep -o '"[a-z0-9_]*":{"activeRun":[a-z]*,"ingestRunId":[a-z0-9]*}'); do
    pair="${pair//\"/}"
    if [[ "$pair" == *activeRun:true* ]]; then
      run="${pair##*ingestRunId:}"
      ACTIVE_RUNS="$ACTIVE_RUNS ${pair%%:*}:${run%\}}"
    else
      inactive="$inactive ${pair%%:*}"
    fi
  done
  if [ "$code" = "200" ] && [ "$(json_field status "$body")" = "ok" ]; then
    ok "ai-server 헬스 — chroma $(json_field chroma "$body"), database $(json_field database "$body"), ACTIVE${ACTIVE_RUNS//:/ run }"
  elif [ "$(json_field database "$body")" = "error" ]; then
    fail "ai-server 헬스 — HTTP $code, DB 연결 실패" "$LOGS postgres ai-server"
  elif [ -n "$inactive" ]; then
    fail "ai-server 헬스 — HTTP $code, ACTIVE run 없는 소스:${inactive}" \
      "make restore-index SNAPSHOT=data/snapshots/snapshot-<소스>-run<id>.tar.gz (소스마다) 후 make up"
  else
    fail "ai-server 헬스 — HTTP $code, chroma $(json_field chroma "$body")" "$LOGS ai-server"
  fi
}

# 3. 소스 목록 — nginx → backend 경로와 활성 소스 수 (API 명세 §2.1)
check_sources() {
  local code body active
  code="$(curl -s -o "$TMP_DIR/sources.json" -w '%{http_code}' --max-time 5 "$BASE_URL/api/v1/sources")" || code="000"
  body="$(cat "$TMP_DIR/sources.json" 2>/dev/null | tr -d ' \r\n')"
  if [ "$code" != "200" ]; then
    [ "$code" = "000" ] && code="응답 없음(5초 초과 또는 연결 실패)" || code="HTTP $code"
    fail "소스 목록 — $code ($BASE_URL/api/v1/sources)" "$LOGS backend nginx"
    return
  fi
  # 활성 run이 있는 소스만 activeRun이 객체다(없으면 null)
  active="$(printf '%s' "$body" | grep -o '"enabled":true,"activeRun":{' | wc -l | tr -d ' ')"
  if [ "$active" -ge "$MIN_SOURCES" ]; then
    ok "소스 목록 — HTTP 200, 활성 소스 ${active}개"
  else
    fail "소스 목록 — 활성 소스 ${active}개 (기대 ${MIN_SOURCES}개 이상)" "ai-server 헬스 항목의 조치를 먼저 따른다"
  fi
}

# 4. 게스트 질문 1회 — nginx 경유 SSE 이벤트 순서(부록 B.1)와 첫 토큰 시간.
# 쿠키를 저장하지 않아 실행마다 새 게스트 세션 1개를 쓴다(IP당 신규 세션 한도 30개/시간, 전시 60개).
check_chat() {
  local payload line event first="" last="" status="" err_code="" tokens=0 t0 ttft="" code total
  if [ "$RUN_LLM" = "0" ]; then
    skip "게스트 질문 — --no-llm"
    return
  fi
  payload="$(printf '{"question":"%s","mode":"SINGLE","sourceKey":"%s"}' "$QUESTION" "$SOURCE_KEY")"
  t0="$(now_ms)"
  while IFS= read -r line; do
    case "$line" in
      data:*) ;;
      *) continue ;;
    esac
    event="$(json_field event "$line")"
    [ -z "$first" ] && first="$event"
    last="$event"
    case "$event" in
      token)
        tokens=$((tokens + 1))
        [ -z "$ttft" ] && ttft=$(($(now_ms) - t0))
        ;;
      done) status="$(json_field status "$line")" ;;
      error) err_code="$(json_field code "$line")" ;;
    esac
  done < <(curl -sN --max-time 40 -D "$TMP_DIR/chat.headers" -H 'Content-Type: application/json' \
    -d "$payload" "$BASE_URL/api/v1/chat/stream" 2>/dev/null)
  total=$(($(now_ms) - t0))
  code="$(grep -m1 '^HTTP/' "$TMP_DIR/chat.headers" 2>/dev/null | cut -d' ' -f2)"

  if [ "${code:-000}" != "200" ]; then
    case "${code:-000}" in
      429) fail "게스트 질문 — HTTP 429 (게스트 신규 세션·채팅 한도)" "1분 뒤 다시 실행. 반복되면 --no-llm 으로 점검" ;;
      000) fail "게스트 질문 — 응답 없음 (40초 초과 또는 연결 실패)" "$LOGS backend ai-server" ;;
      *) fail "게스트 질문 — HTTP $code" "$LOGS backend ai-server" ;;
    esac
  elif [ "$first" = "meta" ] && [ "$tokens" -gt 0 ] && [ "$last" = "done" ] && [ "$status" = "COMPLETED" ]; then
    ok "게스트 질문 — meta → token ${tokens}개 → done(COMPLETED), 첫 토큰 ${ttft}ms, 전체 ${total}ms"
  elif [ -n "$err_code" ]; then
    fail "게스트 질문 — error 이벤트 $err_code (token ${tokens}개)" \
      "$LOGS ai-server — OpenAI 키·사용 한도(잔액) 확인"
  else
    fail "게스트 질문 — 순서 이상: 처음 ${first:-없음}, 끝 ${last:-없음}, done ${status:-없음}, token ${tokens}개" \
      "$LOGS backend ai-server"
  fi
}

# 5. 인덱스 스냅샷 백업 — ACTIVE run마다 snapshot-{source}-run{id}.tar.gz (없으면 경고만)
check_snapshots() {
  local entry source run file missing=""
  if [ -z "$ACTIVE_RUNS" ]; then
    skip "스냅샷 백업 — ACTIVE run을 확인하지 못함"
    return
  fi
  for entry in $ACTIVE_RUNS; do
    source="${entry%%:*}"
    run="${entry##*:}"
    file="snapshot-${source}-run${run}.tar.gz"
    [ -f "$SNAPSHOT_DIR/$file" ] || missing="$missing $run"
  done
  if [ -z "$missing" ]; then
    ok "스냅샷 백업 — ACTIVE run 모두 있음 ($SNAPSHOT_DIR)"
  else
    warn "스냅샷 백업 — 없는 run:$missing" "make snapshot-index RUN=<id> (run마다)"
  fi
}

check_containers
check_ai_health
check_sources
check_chat
check_snapshots

ELAPSED_MS=$(($(now_ms) - START_MS))
if [ "$FAILS" -eq 0 ]; then
  echo "판정: 시연 가능 (경고 ${WARNS}건, $((ELAPSED_MS / 1000))초)"
  exit 0
fi
echo "판정: 시연 불가 — 실패 ${FAILS}건, 경고 ${WARNS}건 ($((ELAPSED_MS / 1000))초)"
exit 1
