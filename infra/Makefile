COMPOSE_BASE = docker-compose.yml
COMPOSE_LOCAL = docker-compose.local.yml
COMPOSE = docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_LOCAL)

.PHONY: up down logs ps build rebuild config

## 전체 스택 기동 (백그라운드)
up:
	$(COMPOSE) up -d

## 전체 스택 종료 (볼륨 보존)
down:
	$(COMPOSE) down

## 전체 스택 종료 + 볼륨 삭제
down-v:
	$(COMPOSE) down -v

## 실시간 로그 출력
logs:
	$(COMPOSE) logs -f

## 서비스 상태 확인
ps:
	$(COMPOSE) ps

## 이미지 빌드 (캐시 사용)
build:
	$(COMPOSE) build

## 이미지 재빌드 (캐시 미사용)
rebuild:
	$(COMPOSE) build --no-cache

## Compose 파일 syntax 검증
config:
	$(COMPOSE) config