#!/usr/bin/env bash
# PostgreSQL 백업 복원 — 정책서 §11 "RPO 24시간, RTO 1시간(복원 리허설 1회)".
#
#   infra/scripts/pg-restore.sh <contextq-YYYYMMDD-HHMM.dump | 로컬 경로>              # 리허설 (기본)
#   infra/scripts/pg-restore.sh <contextq-YYYYMMDD-HHMM.dump | 로컬 경로> --live --yes  # 실제 복원
#
# 리허설: 운영 DB는 건드리지 않는다. 임시 DB(contextq_restore_check)에 복원해 주요 테이블 행 수와
#         소요 시간을 출력하고 임시 DB를 지운다.
# 실제 복원: nginx·backend·ai-server를 멈추고 운영 DB를 백업 시점으로 되돌린 뒤 다시 기동한다.
#            백업 이후 데이터는 사라지므로 --yes가 있어야 실행한다.
set -euo pipefail

# shellcheck source=infra/scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SOURCE="${1:?백업 파일 이름 또는 경로가 필요합니다}"
MODE="rehearsal"
CONFIRMED="no"
shift
for arg in "$@"; do
  case "$arg" in
    --live) MODE="live" ;;
    --yes) CONFIRMED="yes" ;;
    *) die "알 수 없는 옵션: $arg" ;;
  esac
done
[ "$MODE" = "rehearsal" ] || [ "$CONFIRMED" = "yes" ] || die "실제 복원은 --live --yes로만 실행합니다"

DB_USER="$(env_value POSTGRES_USER)"
DB_NAME="$(env_value POSTGRES_DB)"
DB_USER="${DB_USER:-contextq}"
DB_NAME="${DB_NAME:-contextq_db}"
CHECK_DB="contextq_restore_check"
START=$SECONDS

if [ -f "$SOURCE" ]; then
  FILE="$SOURCE"
else
  BACKUP_S3_URI="$(env_value BACKUP_S3_URI)"
  [ -n "$BACKUP_S3_URI" ] || die "운영 환경 파일에 BACKUP_S3_URI가 없습니다"
  FILE="$CONTEXTQ_HOME/backups/$(basename "$SOURCE")"
  echo "== S3에서 받기: $SOURCE"
  aws s3 cp "${BACKUP_S3_URI%/}/$(basename "$SOURCE")" "$FILE" --only-show-errors
fi
[ -s "$FILE" ] || die "백업 파일이 비었거나 없습니다: $FILE"

psql_q() {  # $1 = DB, $2 = SQL
  "$COMPOSE" exec -T postgres psql -U "$DB_USER" -d "$1" -v ON_ERROR_STOP=1 -Atc "$2"
}

COUNT_SQL="SELECT 'app.users', count(*) FROM app.users
UNION ALL SELECT 'app.conversations', count(*) FROM app.conversations
UNION ALL SELECT 'app.messages', count(*) FROM app.messages
UNION ALL SELECT 'ai.ingest_runs', count(*) FROM ai.ingest_runs
UNION ALL SELECT 'ai.index_pointers', count(*) FROM ai.index_pointers"

if [ "$MODE" = "rehearsal" ]; then
  echo "== 리허설: 임시 DB $CHECK_DB에 복원 (운영 DB 변경 없음)"
  "$COMPOSE" exec -T postgres dropdb -U "$DB_USER" --if-exists "$CHECK_DB"
  "$COMPOSE" exec -T postgres createdb -U "$DB_USER" "$CHECK_DB"
  "$COMPOSE" exec -T postgres pg_restore -U "$DB_USER" -d "$CHECK_DB" --no-owner --exit-on-error < "$FILE"
  echo "== 행 수 (임시 DB)"
  psql_q "$CHECK_DB" "$COUNT_SQL" | tr '|' '\t'
  "$COMPOSE" exec -T postgres dropdb -U "$DB_USER" "$CHECK_DB"
  echo "리허설 완료: $((SECONDS - START))초 (RTO 목표 1시간)"
  exit 0
fi

echo "== 실제 복원: 서비스 정지"
"$COMPOSE" stop nginx backend ai-server
echo "== $DB_NAME 복원 (백업 이후 데이터는 사라진다)"
"$COMPOSE" exec -T postgres pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner \
  --exit-on-error < "$FILE"
psql_q "$DB_NAME" "$COUNT_SQL" | tr '|' '\t'
echo "== 서비스 기동"
"$COMPOSE" up -d --no-build
wait_healthy "${HEALTH_TIMEOUT:-300}" postgres ai-server backend nginx || die "복원 후 헬스체크 실패"
echo "복원 완료: $((SECONDS - START))초"
