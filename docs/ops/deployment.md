# 배포 환경 구성 및 운영 절차

## 환경 종류

| 환경 | 목적 | 접근 방법 |
|---|---|---|
| local | 개발·테스트 | `make up` (docker compose local override) |
| production | 서비스 운영 | GHCR 이미지 pull + docker compose up |

## 로컬 기동

```bash
cd infra
cp ../.env.example .env  # .env 값 채우기
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

## 프로덕션 배포

(추후 작성)