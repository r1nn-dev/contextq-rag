#!/usr/bin/env bash
# git SHA 기반 배포·롤백 — 정책서 §9.4 "이미지 태그 = git SHA, 롤백 = 직전 SHA로 재실행, latest 금지".
#
#   infra/scripts/deploy.sh <40자 git SHA>        # 배포 (release.yml이 올린 이미지)
#   infra/scripts/deploy.sh --previous            # 지금 SHA가 아닌, 가장 최근에 성공한 배포 SHA 출력
#   infra/scripts/deploy.sh "$(infra/scripts/deploy.sh --previous)"   # 롤백
#
# 순서: 저장소를 같은 SHA로 체크아웃(Compose·nginx 설정 일치) → release.env 기록 → 이미지 pull
#       → postgres·ai-server 기동·헬스체크 → 전체 기동·헬스체크 → 이력 기록.
# ai-server는 소스별 ACTIVE 인덱스가 있어야 healthy다. 첫 배포에서 인덱스가 없으면 복원 안내를 내고 멈춘다.
set -euo pipefail

# shellcheck source=infra/scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"

usage() {
  sed -n '2,9p' "$0" >&2
  exit 2
}

# 이력 형식: "<UTC 시각> <sha> <ok|failed|waiting-index>"
# 직전 배포 = 지금 배포 중인 SHA가 아닌, 가장 최근에 성공한 SHA
previous_ok() {
  local current
  current="$(env_value IMAGE_TAG "$RELEASE_FILE")"
  [ -f "$HISTORY_FILE" ] || return 0
  awk -v cur="$current" '$3 == "ok" && $2 != cur { last = $2 } END { if (last) print last }' "$HISTORY_FILE"
}

record() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1 $2" >> "$HISTORY_FILE"
}

case "${1:-}" in
  --previous)
    prev="$(previous_ok)"
    [ -n "$prev" ] || die "되돌릴 이전 배포가 없습니다 ($HISTORY_FILE)"
    echo "$prev"
    exit 0
    ;;
  "" | -h | --help) usage ;;
esac

SHA="$1"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "40자 소문자 git SHA만 받습니다: $SHA"
[ -f "$ENV_FILE" ] || die "운영 환경 파일이 없습니다: $ENV_FILE"
[ -d "$APP_DIR/.git" ] || die "저장소 체크아웃이 없습니다: $APP_DIR"

REGISTRY="$(env_value IMAGE_REGISTRY)"
[ -n "$REGISTRY" ] || die "운영 환경 파일에 IMAGE_REGISTRY가 없습니다 (예: ghcr.io/<owner>/<repo>)"

PREV_RELEASE=""
[ -f "$RELEASE_FILE" ] && PREV_RELEASE="$(cat "$RELEASE_FILE")"
PREV_SHA="$(env_value IMAGE_TAG "$RELEASE_FILE")"

restore_previous() {  # pull 단계 실패 시 이전 상태로 되돌린다 (컨테이너는 아직 그대로)
  if [ -n "$PREV_RELEASE" ]; then
    printf '%s\n' "$PREV_RELEASE" > "$RELEASE_FILE"
    if [ -n "$PREV_SHA" ]; then
      git -C "$APP_DIR" checkout --quiet --detach "$PREV_SHA" || true
    fi
  else
    rm -f "$RELEASE_FILE"
  fi
}

echo "== 1/5 저장소 체크아웃 $SHA"
git -C "$APP_DIR" fetch --quiet origin
git -C "$APP_DIR" cat-file -e "${SHA}^{commit}" 2>/dev/null || die "원격 저장소에 없는 커밋입니다: $SHA"
git -C "$APP_DIR" checkout --quiet --detach "$SHA"

echo "== 2/5 이미지 pull ($REGISTRY/*:$SHA)"
printf 'IMAGE_REGISTRY=%s\nIMAGE_TAG=%s\n' "$REGISTRY" "$SHA" > "$RELEASE_FILE"
ROLLBACK="$(previous_ok)"  # 이번 대상이 아닌, 가장 최근에 성공한 SHA
if ! "$COMPOSE" pull --quiet; then
  restore_previous
  die "이미지 pull 실패 — release.yml 실행 여부와 GHCR 로그인(read:packages)을 확인하세요. 변경 없음"
fi

echo "== 3/5 postgres·ai-server 기동 (ai 스키마 마이그레이션 포함)"
"$COMPOSE" up -d --no-build postgres ai-server
if ! wait_healthy "$HEALTH_TIMEOUT" postgres ai-server; then
  if "$COMPOSE" exec -T ai-server python -c \
      "import urllib.request,urllib.error,sys
try: urllib.request.urlopen('http://localhost:8000/internal/v1/health', timeout=4)
except urllib.error.HTTPError as e: sys.exit(0 if e.code == 503 else 1)
sys.exit(1)" 2>/dev/null; then
    record "$SHA" waiting-index
    echo "ai-server가 degraded(503)입니다 — 소스별 ACTIVE 인덱스가 없습니다." >&2
    echo "  infra/scripts/restore-index.sh <snapshot-{source_key}-run{id}.tar.gz>  (소스마다)" >&2
    echo "  복원 후 다시: infra/scripts/deploy.sh $SHA" >&2
    exit 3
  fi
  record "$SHA" failed
  die "ai-server 기동 실패 — 로그: $COMPOSE logs ai-server${ROLLBACK:+ / 롤백: deploy.sh $ROLLBACK}"
fi

echo "== 4/5 전체 기동"
"$COMPOSE" up -d --no-build --remove-orphans
if ! wait_healthy "$HEALTH_TIMEOUT" postgres ai-server backend nginx; then
  record "$SHA" failed
  die "헬스체크 실패 — 로그: $COMPOSE logs${ROLLBACK:+ / 롤백: deploy.sh $ROLLBACK}"
fi

echo "== 5/5 기록"
record "$SHA" ok
"$COMPOSE" ps
echo "배포 완료: $SHA${ROLLBACK:+ (롤백: deploy.sh $ROLLBACK)}"
