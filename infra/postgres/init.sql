-- init.sql
-- 역할: Docker postgres /docker-entrypoint-initdb.d/ 훅에서 1회 실행
-- 주의: postgres_data Named Volume이 이미 존재하면 이 파일은 실행되지 않음

-- POSTGRES_DB 환경 변수로 contextq DB가 이미 생성됨 → CREATE DATABASE 불필요
-- DDL(테이블/인덱스 생성)은 Flyway V1__init_schema.sql 이후에서 관리 → 여기에 작성 금지

-- (선택) 애플리케이션 전용 역할 — 필요 시 주석 해제
-- CREATE ROLE app_user WITH LOGIN PASSWORD 'change_me';
-- GRANT ALL PRIVILEGES ON DATABASE contextq TO app_user;