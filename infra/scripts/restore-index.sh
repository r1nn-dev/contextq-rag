#!/usr/bin/env bash
# 운영 서버 인덱스 복원 — S3 스냅샷을 받아 같은 run id로 복원·검증·활성화한다 (정책서 §4.5, ADR-005).
#
#   infra/scripts/restore-index.sh <snapshot-{source_key}-run{id}.tar.gz> [--no-activate]
#
# - 운영 환경 파일의 SNAPSHOT_S3_URI에서 받아 ${CONTEXTQ_HOME}/snapshots에 두고 sha256을 확인한다.
# - ai-server 컨테이너 안에서 `python -m src.ingest.cli restore`를 실행한다(prod 프로필에서도 등록된 명령).
#   스모크 질문 5개를 임베딩하므로 OPENAI_API_KEY가 필요하다(컨테이너 환경에 이미 있음).
# - 같은 run id가 이미 있으면 거부된다. 실패 run은 FAILED로 남고 기존 ACTIVE는 그대로다.
set -euo pipefail

# shellcheck source=infra/scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NAME="${1:?스냅샷 파일 이름이 필요합니다 (예: snapshot-langchain_v1x-run10.tar.gz)}"
ACTIVATE="--activate"
[ "${2:-}" = "--no-activate" ] && ACTIVATE=""

SNAPSHOT_S3_URI="$(env_value SNAPSHOT_S3_URI)"
[ -n "$SNAPSHOT_S3_URI" ] || die "운영 환경 파일에 SNAPSHOT_S3_URI가 없습니다"
export SNAPSHOT_S3_URI

SNAPSHOT_DIR="$(env_value SNAPSHOT_HOST_DIR)"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$CONTEXTQ_HOME/snapshots}"

if [ -f "$SNAPSHOT_DIR/$NAME" ] && (cd "$SNAPSHOT_DIR" && sha256sum -c --status "$NAME.sha256" 2>/dev/null); then
  echo "== 이미 받은 스냅샷 사용: $SNAPSHOT_DIR/$NAME"
else
  echo "== S3에서 받기"
  "$SCRIPTS_DIR/index-snapshot-s3.sh" download "$NAME" "$SNAPSHOT_DIR"
fi

echo "== ai-server 준비"
"$COMPOSE" up -d --no-build postgres ai-server

echo "== 복원 ($NAME${ACTIVATE:+ → 활성화})"
# shellcheck disable=SC2086 # ACTIVATE는 비어 있거나 옵션 하나
"$COMPOSE" exec -T ai-server python -m src.ingest.cli restore \
  --snapshot "/app/data/snapshots/$NAME" $ACTIVATE

echo "완료 — 모든 소스를 복원했으면 infra/scripts/deploy.sh <git-sha>를 다시 실행하세요(첫 배포)."
