# ---- frontend (Vite → dist-web) ----
FROM node:22-alpine AS build

WORKDIR /build/web

COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

COPY web/ ./
RUN npm run build

# ---- static server ----
FROM nginx:1.27-alpine

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/web/dist-web /usr/share/nginx/html

EXPOSE 80
