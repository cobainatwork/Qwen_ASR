# syntax=docker/dockerfile:1.7
# Frontend dev container — Next.js 14 dev server on Linux.
# Production build (npm run build + next start) is intentionally not wired here
# yet; this image targets the "edit on Windows → git push → Linux pull → docker
# compose up" loop established 2026-05-20.

FROM node:20-alpine AS deps
WORKDIR /app

# Install deps via lockfile so the dev image matches CI.
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS dev
WORKDIR /app

# Pull pre-installed node_modules from the deps stage; source is bind-mounted by
# docker-compose at runtime so git pull on the host reflects without rebuild.
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.js dev server inside a container can miss inotify events on bind mounts;
# fall back to polling so file edits on the host actually trigger Fast Refresh.
ENV NODE_ENV=development
ENV WATCHPACK_POLLING=true
ENV CHOKIDAR_USEPOLLING=true

EXPOSE 3000

CMD ["npm", "run", "dev"]
