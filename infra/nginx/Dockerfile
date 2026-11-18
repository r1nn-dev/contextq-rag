# nginx 이미지 — React 빌드 결과를 직접 서빙하고 /api/**를 backend로 넘긴다 (기획서 §4.1, 컨테이너 4개).
# 빌드 컨텍스트는 frontend/, nginx 설정은 추가 컨텍스트 `nginxconf`(infra/nginx/)에서 받는다.
#   docker build -f infra/nginx/Dockerfile --build-context nginxconf=infra/nginx frontend

# stage 1: frontend build
FROM node:20-alpine AS build
WORKDIR /app

# package 파일을 먼저 복사해 의존성 레이어를 캐시한다
COPY package.json package-lock.json ./
RUN npm ci --silent

COPY . .
RUN npm run build

# stage 2: runtime
FROM nginx:1.27-alpine AS runtime

# 레이트 리밋 기본값 — 정책서 §8.1. 전시회 조정은 기동 시 환경 변수로 덮어쓴다
ENV NGINX_RATE_AUTH=10r/m NGINX_BURST_AUTH=5 \
    NGINX_RATE_CHAT=30r/m NGINX_BURST_CHAT=10 \
    NGINX_RATE_API=120r/m NGINX_BURST_API=30

# 기본 server 설정을 지우고 우리 설정만 둔다. templates/*.template은 기동 시 envsubst로 conf.d에 풀린다
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=nginxconf nginx.conf /etc/nginx/nginx.conf
COPY --from=nginxconf snippets/ /etc/nginx/snippets/
COPY --from=nginxconf templates/ /etc/nginx/templates/
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
