#!/usr/bin/env bash
# 운영 스크립트 공용 함수 — 다른 스크립트가 source한다 (직접 실행하지 않음).
# shellcheck disable=SC2034 # 이 파일의 변수는 source한 스크립트가 쓴다

CONTEXTQ_HOME="${CONTEXTQ_HOME:-/opt/contextq}"
APP_DIR="${CONTEXTQ_HOME}/app"
ENV_FILE="${CONTEXTQ_HOME}/contextq.env"
RELEASE_FILE="${CONTEXTQ_HOME}/release.env"
HISTORY_FILE="${CONTEXTQ_HOME}/deployments.log"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="${SCRIPTS_DIR}/compose-prod.sh"

die() {
  echo "오류: $*" >&2
  exit 1
}

# 운영 환경 파일에서 KEY의 값을 읽는다. source하지 않는 이유: BCrypt 해시($2a$…) 같은 값이
# 셸 확장으로 깨지지 않게 하려고. 없으면 빈 문자열.
env_value() {
  local key="$1" file="${2:-$ENV_FILE}"
  [ -f "$file" ] || return 0
  grep -m1 "^${key}=" "$file" | cut -d= -f2- || true
}

# 운영 환경 파일의 KEY를 VALUE로 바꾼다(없으면 추가). 파일 권한은 유지한다.
set_env_value() {
  local key="$1" value="$2" file="${3:-$ENV_FILE}" tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" "$file"; then
    awk -v k="$key" -v v="$value" 'BEGIN { FS = OFS = "=" } $1 == k { print k "=" v; next } { print }' \
      "$file" > "$tmp"
  else
    cat "$file" > "$tmp"
    echo "${key}=${value}" >> "$tmp"
  fi
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

# 서비스들이 healthy가 될 때까지 기다린다. 제한 시간을 넘기면 1을 돌려준다.
wait_healthy() {
  local timeout="$1"
  shift
  local deadline=$((SECONDS + timeout)) service status pending
  while :; do
    pending=""
    for service in "$@"; do
      status="$("$COMPOSE" ps --format '{{.Health}}' "$service" 2>/dev/null | head -n1)"
      [ "$status" = "healthy" ] || pending="$pending $service(${status:-없음})"
    done
    [ -z "$pending" ] && return 0
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "헬스체크 대기 시간 초과:$pending" >&2
      return 1
    fi
    sleep 5
  done
}
