#!/usr/bin/env bash
# 메모리 실측 보고 — 배포 직후 기획서 부록 A 예산표를 실측값으로 바꾸는 데 쓴다.
#
#   infra/scripts/mem-report.sh            # 마크다운 표 출력 (docs·개발 일지에 붙여 넣기)
#
# 부록 A 예산: 상주 합계 ≤ 1.75GB, 평시 스왑 ≤ 256MB (정책서 §11).
set -euo pipefail

echo "측정 시각: $(date '+%Y-%m-%d %H:%M %Z') · 호스트: $(hostname)"
echo
echo "| 구성요소 | 사용 / 상한 | 비율 |"
echo "| --- | --- | --- |"
docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}|{{.MemPerc}}' \
  | grep '^contextq-' | sort \
  | awk -F'|' '{ printf "| %s | %s | %s |\n", $1, $2, $3 }'
echo
free -m | awk '
  /^Mem:/  { printf "- 호스트 메모리: 사용 %d MB / 전체 %d MB (가용 %d MB)\n", $3, $2, $7 }
  /^Swap:/ { printf "- 스왑: 사용 %d MB / 전체 %d MB\n", $3, $2 }'
echo "- 컨테이너 합계: $(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep '^contextq-' \
  | awk '{ v = $2; u = v; sub(/[0-9.]+/, "", u); sub(/[A-Za-z]+$/, "", v);
           f = (u == "GiB") ? 1024 : (u == "KiB") ? 1 / 1024 : 1; s += v * f }
         END { printf "%.0f MB", s }')"
