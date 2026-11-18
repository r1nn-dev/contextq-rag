#!/usr/bin/env bash
# 전시회 당일 한도 전환·원복 — 정책서 §8.1 "11/18 전시회 당일 한정", §9.4.
#
#   scripts/exhibition-profile.sh apply     # 채팅 60r/m(burst 20), 게스트 신규 세션 IP당 60개/시간
#   scripts/exhibition-profile.sh reset     # 기본값 30r/m(burst 10), 30개/시간 (다음 날 00:00)
#   scripts/exhibition-profile.sh status    # 운영 환경 파일의 현재 값
#
# 운영 서버에서 실행한다. 운영 환경 파일의 값을 바꾸고 nginx·backend 컨테이너만 다시 만든다
# (backend 재기동 동안 약 1분 새 질문이 실패할 수 있으므로 관람객이 적을 때 실행).
# 리허설 결과 수치가 부족하면 apply 전에 EXHIBITION_CHAT_RATE·EXHIBITION_CHAT_BURST·
# EXHIBITION_GUEST_SESSIONS로 값을 바꿔 실행한다(정책서 §8.1 "apply 실행 전 파라미터 조정 가능").
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=infra/scripts/lib.sh
. "$REPO_ROOT/infra/scripts/lib.sh"

KEYS=(NGINX_RATE_CHAT NGINX_BURST_CHAT GUEST_SESSIONS_PER_IP_PER_HOUR)

case "${1:-}" in
  apply) VALUES=("${EXHIBITION_CHAT_RATE:-60r/m}" "${EXHIBITION_CHAT_BURST:-20}" "${EXHIBITION_GUEST_SESSIONS:-60}") ;;
  reset) VALUES=("30r/m" "10" "30") ;;
  status)
    for key in "${KEYS[@]}"; do
      printf '%s=%s\n' "$key" "$(env_value "$key")"
    done
    exit 0
    ;;
  *)
    sed -n '2,6p' "$0" >&2
    exit 2
    ;;
esac

[ -f "$ENV_FILE" ] || die "운영 환경 파일이 없습니다: $ENV_FILE"
[[ "${VALUES[0]}" =~ ^[0-9]+r/m$ ]] || die "채팅 한도 형식은 <숫자>r/m 입니다: ${VALUES[0]}"
[[ "${VALUES[1]}" =~ ^[0-9]+$ && "${VALUES[2]}" =~ ^[0-9]+$ ]] || die "burst·게스트 세션 수는 정수여야 합니다"

for i in "${!KEYS[@]}"; do
  set_env_value "${KEYS[$i]}" "${VALUES[$i]}"
  echo "${KEYS[$i]}=${VALUES[$i]}"
done

# 바뀐 환경 변수를 쓰는 컨테이너만 다시 만든다 (postgres·ai-server는 그대로)
"$COMPOSE" up -d --no-build nginx backend
wait_healthy "${HEALTH_TIMEOUT:-300}" backend nginx || die "재기동 후 헬스체크 실패 — $COMPOSE logs nginx backend"
echo "$1 완료 ($(date '+%F %T'))"
