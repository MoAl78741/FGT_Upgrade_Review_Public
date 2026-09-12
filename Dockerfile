FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY scripts/build-api.cjs /app/scripts/build-api.cjs
RUN npm run build

FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/app/data/fgt_upgrade.db UPLOADS_DIR=/app/uploads
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends libseccomp2 libfontconfig1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
RUN groupadd --gid 10001 appgroup && useradd --uid 10001 --gid appgroup --no-create-home appuser
COPY backend/ ./backend/
COPY fgt_upgrade/ ./fgt_upgrade/
COPY LICENSE THIRD_PARTY_NOTICES.md TEAM_INSTALLATION.md OPERATIONS.md API_GUIDE.md ./
COPY licenses/ ./licenses/
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/LICENSE ./licenses/NODE-LICENSE
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
RUN mkdir -p /app/data /app/uploads /system && chown appuser:appgroup /app/data /app/uploads /system
USER 10001:10001
# Identity belongs after dependency layers so a new build number does not reinstall them.
ARG BUILD_NUMBER=dev
ARG BUILD_REVISION=
ARG APP_EDITION=public
ENV TEAM_AUTH_ENABLED=true APP_BUILD_NUMBER=${BUILD_NUMBER} APP_BUILD_REVISION=${BUILD_REVISION} APP_EDITION=${APP_EDITION}
LABEL org.opencontainers.image.version="3.0.0" org.opencontainers.image.revision=${BUILD_REVISION}
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=120s CMD ["python", "-m", "backend.healthcheck"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
