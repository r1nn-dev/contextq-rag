# stage 1: build
FROM node:20-alpine AS build
WORKDIR /app

# copy package files first to cache the dependency layer
# source changes will not trigger npm ci re-run
COPY package.json package-lock.json ./
RUN npm ci --silent

COPY . .
RUN npm run build

# stage 2: runtime (nginx only; no Node.js runtime)
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# 'daemon off;' keeps nginx in the foreground so the container stays alive
CMD ["nginx", "-g", "daemon off;"]