# syntax=docker/dockerfile:1
# Frontend image for the AI Chat app (Next.js "standalone" output).
# Build from the frontend/ folder:
#   docker build -t ai-chat-frontend:dev \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .
ARG NODE_VERSION=24

# ---------- Stage 1: install dependencies ----------
FROM node:${NODE_VERSION}-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# ---------- Stage 2: build ----------
FROM node:${NODE_VERSION}-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are copied INTO the JavaScript at build time and are visible
# to every visitor. Only public values go here, never secrets (Chapter 17).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- Stage 3: runtime ----------
FROM node:${NODE_VERSION}-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The standalone folder already contains the few node_modules the server needs
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# The official node image ships a non-root user called "node"
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", \
        "fetch('http://127.0.0.1:3000/').then(r=>process.exit(+!r.ok),()=>process.exit(1))"]

CMD ["node", "server.js"]
