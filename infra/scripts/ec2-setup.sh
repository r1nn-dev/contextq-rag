#!/usr/bin/env bash
# EC2 초기 설정 (Ubuntu 24.04 LTS, 1회) — 기획서 결정 6·부록 A, 정책서 §9.4.
#
#   sudo bash infra/scripts/ec2-setup.sh [운영 사용자 (기본 ubuntu)]
#
# 하는 일 (다시 실행해도 같은 결과):
#   - 시간대 Asia/Seoul (백업 크론 03:00 KST 기준)
#   - 스왑 2GiB + vm.swappiness=10 (2GiB 메모리 OOM 안전망)
#   - Docker Engine + Compose 플러그인, 운영 사용자를 docker 그룹에 추가
#   - AWS CLI(S3 스냅샷·백업), certbot(Let's Encrypt), git
#   - 운영 디렉터리 /opt/contextq/{snapshots,backups,logs}
# AWS 쪽 설정(인스턴스 유형·CPU standard 모드·EBS·Elastic IP·보안 그룹·IAM 역할)은 콘솔에서 한다
# (docs/ops/deployment.md §5.1).
set -euo pipefail

OWNER="${1:-ubuntu}"
CONTEXTQ_HOME="${CONTEXTQ_HOME:-/opt/contextq}"
SWAP_FILE=/swapfile

[ "$(id -u)" -eq 0 ] || { echo "root 권한으로 실행하세요 (sudo)" >&2; exit 1; }
id "$OWNER" >/dev/null 2>&1 || { echo "사용자가 없습니다: $OWNER" >&2; exit 1; }

log() { printf '\n== %s\n' "$*"; }

log "시간대 Asia/Seoul"
timedatectl set-timezone Asia/Seoul

log "스왑 2GiB, swappiness=10"
if ! swapon --show=NAME --noheadings | grep -qx "$SWAP_FILE"; then
  [ -f "$SWAP_FILE" ] || fallocate -l 2G "$SWAP_FILE"
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE" >/dev/null
  swapon "$SWAP_FILE"
fi
grep -q "^$SWAP_FILE " /etc/fstab || echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
echo "vm.swappiness=10" > /etc/sysctl.d/99-contextq.conf
sysctl -q --system

log "Docker Engine + Compose 플러그인"
if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -y -q ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091 # 실행 중인 OS의 버전 이름을 읽는다
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
usermod -aG docker "$OWNER"

log "git · certbot · AWS CLI"
apt-get install -y -q git certbot
command -v aws >/dev/null || snap install aws-cli --classic

log "운영 디렉터리 $CONTEXTQ_HOME"
install -d -o "$OWNER" -g "$OWNER" -m 0755 "$CONTEXTQ_HOME" \
  "$CONTEXTQ_HOME/snapshots" "$CONTEXTQ_HOME/backups" "$CONTEXTQ_HOME/logs"

log "완료"
docker --version
docker compose version
free -h
echo "다음: 저장소 체크아웃·운영 환경 파일 작성·인증서 발급 (docs/ops/deployment.md §5.2)"
echo "docker 그룹 반영을 위해 $OWNER 사용자로 다시 로그인하세요."
