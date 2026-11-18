#!/usr/bin/env bash
# 운영 서버 docker compose 래퍼 — 모든 운영 스크립트가 같은 파일·환경으로 Compose를 부른다.
#
#   infra/scripts/compose-prod.sh ps
#   infra/scripts/compose-prod.sh logs -f backend
#
# 운영 디렉터리 (CONTEXTQ_HOME, 기본 /opt/contextq — docs/ops/deployment.md §5)
#   app/            저장소 체크아웃 (deploy.sh가 배포 SHA로 맞춘다)
#   contextq.env    비밀값·운영 설정 (chmod 600, 저장소에 두지 않음)
#   release.env     배포 중인 이미지 (IMAGE_REGISTRY·IMAGE_TAG, deploy.sh가 쓴다)
set -euo pipefail

# shellcheck source=infra/scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[ -f "$ENV_FILE" ] || { echo "운영 환경 파일이 없습니다: $ENV_FILE" >&2; exit 1; }
[ -f "$RELEASE_FILE" ] || { echo "배포 기록이 없습니다: $RELEASE_FILE (deploy.sh <git-sha>를 먼저 실행)" >&2; exit 1; }

exec docker compose \
  --env-file "$ENV_FILE" \
  --env-file "$RELEASE_FILE" \
  -f "$APP_DIR/infra/docker-compose.yml" \
  -f "$APP_DIR/infra/docker-compose.prod.yml" \
  "$@"
