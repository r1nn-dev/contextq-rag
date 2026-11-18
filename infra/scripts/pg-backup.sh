#!/usr/bin/env bash
# PostgreSQL 일일 백업 → S3, 7일 보관 — 정책서 §9.4 "일 1회 pg_dump → S3, 7일 보관" (RPO 24시간).
#
#   infra/scripts/pg-backup.sh          # 크론이 매일 03:00 KST에 실행 (ec2-setup.sh가 등록)
#
# - 운영 환경 파일의 BACKUP_S3_URI(예: s3://<bucket>/pg-backups)에 contextq-YYYYMMDD-HHMM.dump(-Fc)로 올린다.
# - S3에서 7일보다 오래된 백업을 지우고, 서버에는 최근 2개만 남긴다.
# - 인덱스는 스냅샷이 백업이다(정책서 §9.4). 이 스크립트는 DB만 다룬다.
set -euo pipefail

# shellcheck source=infra/scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_S3_URI="$(env_value BACKUP_S3_URI)"
[ -n "$BACKUP_S3_URI" ] || die "운영 환경 파일에 BACKUP_S3_URI가 없습니다"
BACKUP_S3_URI="${BACKUP_S3_URI%/}"
DB_USER="$(env_value POSTGRES_USER)"
DB_NAME="$(env_value POSTGRES_DB)"
DB_USER="${DB_USER:-contextq}"
DB_NAME="${DB_NAME:-contextq_db}"

BACKUP_DIR="$CONTEXTQ_HOME/backups"
mkdir -p "$BACKUP_DIR"
NAME="contextq-$(TZ=Asia/Seoul date +%Y%m%d-%H%M).dump"

echo "$(date '+%F %T') 백업 시작: $NAME"
"$COMPOSE" exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$BACKUP_DIR/$NAME.part"
[ -s "$BACKUP_DIR/$NAME.part" ] || die "pg_dump 결과가 비었습니다"
mv "$BACKUP_DIR/$NAME.part" "$BACKUP_DIR/$NAME"
aws s3 cp "$BACKUP_DIR/$NAME" "$BACKUP_S3_URI/$NAME" --only-show-errors

# 서버에는 최근 2개만 (EBS 20GiB, 정책서 §11 디스크 사용률 ≤ 70%)
find "$BACKUP_DIR" -maxdepth 1 -name 'contextq-*.dump' -printf '%T@ %p\n' \
  | sort -rn | tail -n +3 | cut -d' ' -f2- | xargs -r rm -f

# S3 보관 기간 정리 — 파일 이름의 KST 날짜 기준
CUTOFF="$(TZ=Asia/Seoul date -d "$RETENTION_DAYS days ago" +%Y%m%d)"
aws s3 ls "$BACKUP_S3_URI/" | awk '{ print $4 }' \
  | grep -E '^contextq-[0-9]{8}-[0-9]{4}\.dump$' \
  | while read -r key; do
      day="${key:9:8}"
      if [ "$day" -lt "$CUTOFF" ]; then
        aws s3 rm "$BACKUP_S3_URI/$key" --only-show-errors
        echo "보관 기간 지난 백업 삭제: $key"
      fi
    done

echo "$(date '+%F %T') 백업 완료: $BACKUP_S3_URI/$NAME ($(du -h "$BACKUP_DIR/$NAME" | cut -f1))"
