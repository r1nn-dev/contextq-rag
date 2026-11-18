#!/usr/bin/env bash
# Let's Encrypt 인증서 발급 (1회) — 정책서 §11 "HTTPS 전용".
#
#   sudo bash infra/scripts/tls-init.sh <도메인> <알림 이메일>
#
# - nginx가 80 포트를 쓰기 전에 standalone 모드로 발급한다(첫 배포 전 실행).
# - 갱신은 certbot 기본 타이머가 한다. 갱신 때만 nginx를 잠시 멈추고 다시 띄우도록 훅을 함께 저장한다
#   (60일마다 수 초 중단 — 단일 인스턴스 운영에서 허용, docs/ops/deployment.md §5.3).
set -euo pipefail

DOMAIN="${1:?도메인이 필요합니다 (예: contextq.example.com)}"
EMAIL="${2:?만료 알림을 받을 이메일이 필요합니다}"
CONTEXTQ_HOME="${CONTEXTQ_HOME:-/opt/contextq}"
COMPOSE="$CONTEXTQ_HOME/app/infra/scripts/compose-prod.sh"

[ "$(id -u)" -eq 0 ] || { echo "root 권한으로 실행하세요 (sudo)" >&2; exit 1; }
[ -x "$COMPOSE" ] || { echo "저장소 체크아웃이 없습니다: $COMPOSE" >&2; exit 1; }

certbot certonly --standalone --non-interactive --agree-tos \
  -m "$EMAIL" -d "$DOMAIN" \
  --pre-hook "CONTEXTQ_HOME=$CONTEXTQ_HOME $COMPOSE stop nginx || true" \
  --post-hook "CONTEXTQ_HOME=$CONTEXTQ_HOME $COMPOSE start nginx || true"

certbot renew --dry-run
echo "발급 완료: /etc/letsencrypt/live/$DOMAIN/ — 운영 환경 파일의 DOMAIN=$DOMAIN 확인"
