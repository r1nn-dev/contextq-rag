#!/usr/bin/env bash
# 인덱스 스냅샷 S3 업로드·다운로드 (정책서 §4.5 "스냅샷 보관", ADR-005).
#
#   SNAPSHOT_S3_URI=s3://<bucket>/index-snapshots infra/scripts/index-snapshot-s3.sh upload <snapshot.tar.gz>
#   SNAPSHOT_S3_URI=s3://<bucket>/index-snapshots infra/scripts/index-snapshot-s3.sh download <snapshot-이름.tar.gz> [저장 디렉터리]
#   SNAPSHOT_S3_URI=s3://<bucket>/index-snapshots infra/scripts/index-snapshot-s3.sh list
#
# - 스냅샷은 run별로 보관하고 최종 발표(12/10)까지 지우지 않는다. 같은 이름이 S3에 있으면 업로드를 거부한다.
# - 업로드 전과 다운로드 후에 `.sha256` 파일로 전송 손상을 확인한다. 손상된 파일은 복원하지 않는다
#   (복원 실패 run은 같은 run id로 다시 복원할 수 없으므로 복원 전에 걸러낸다).
# - AWS 자격 증명은 aws CLI 기본 체인(EC2 인스턴스 역할 또는 별도 터미널의 프로필)으로만 받는다.
set -euo pipefail

usage() {
  sed -n '2,6p' "$0" >&2
  exit 2
}

: "${SNAPSHOT_S3_URI:?SNAPSHOT_S3_URI가 필요합니다 (예: s3://<bucket>/index-snapshots)}"
S3_PREFIX="${SNAPSHOT_S3_URI%/}"

command -v aws >/dev/null || { echo "aws CLI가 필요합니다" >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "sha256sum이 필요합니다" >&2; exit 1; }

check_name() {
  case "$1" in
    snapshot-*-run*.tar.gz) ;;
    *) echo "스냅샷 이름 형식이 아닙니다: $1 (snapshot-{source_key}-run{id}.tar.gz)" >&2; exit 2 ;;
  esac
}

verify() {  # $1 = 디렉터리, $2 = 스냅샷 파일 이름
  (cd "$1" && sha256sum -c --status "$2.sha256") || {
    echo "checksum 불일치: $1/$2 — 파일을 다시 받으세요" >&2
    exit 1
  }
}

upload() {
  local file="${1:?업로드할 스냅샷 파일이 필요합니다}"
  local dir name
  dir="$(cd "$(dirname "$file")" && pwd)"
  name="$(basename "$file")"
  check_name "$name"
  [ -f "$dir/$name.sha256" ] || { echo "$name.sha256이 없습니다 (make snapshot-index가 함께 만든다)" >&2; exit 1; }
  verify "$dir" "$name"
  if aws s3 ls "$S3_PREFIX/$name" >/dev/null 2>&1; then
    echo "이미 S3에 있습니다: $S3_PREFIX/$name (run별 보관, 덮어쓰지 않음)" >&2
    exit 1
  fi
  aws s3 cp "$dir/$name.sha256" "$S3_PREFIX/$name.sha256" --only-show-errors
  aws s3 cp "$dir/$name" "$S3_PREFIX/$name" --only-show-errors
  echo "업로드 완료: $S3_PREFIX/$name"
}

download() {
  local name="${1:?받을 스냅샷 이름이 필요합니다}"
  local dest="${2:-.}"
  check_name "$name"
  mkdir -p "$dest"
  aws s3 cp "$S3_PREFIX/$name.sha256" "$dest/$name.sha256" --only-show-errors
  aws s3 cp "$S3_PREFIX/$name" "$dest/$name" --only-show-errors
  verify "$dest" "$name"
  echo "다운로드·checksum 확인 완료: $dest/$name"
}

case "${1:-}" in
  upload) shift; upload "$@" ;;
  download) shift; download "$@" ;;
  list) aws s3 ls "$S3_PREFIX/" | grep -E 'snapshot-.*\.tar\.gz$' || true ;;
  *) usage ;;
esac
