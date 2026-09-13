FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
COPY vendor/npm/ /vendor/npm/
RUN npm ci --offline --cache /vendor/npm --no-audit --no-fund
COPY frontend/ ./
COPY scripts/build-api.cjs /app/scripts/build-api.cjs
RUN npm run build

FROM python:3.12-slim-trixie@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/app/data/fgt_upgrade.db UPLOADS_DIR=/app/uploads
COPY vendor/debian/linux-amd64/ /vendor/debian/
RUN dpkg -i /vendor/debian/*.deb && rm -rf /vendor/debian /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
COPY vendor/python/linux-amd64/ /vendor/python/
RUN pip install --no-index --find-links /vendor/python --no-cache-dir --require-hashes -r requirements.lock && rm -rf /vendor/python
RUN groupadd --gid 10001 appgroup && useradd --uid 10001 --gid appgroup --no-create-home appuser
COPY backend/ ./backend/
COPY fgt_upgrade/ ./fgt_upgrade/
COPY LICENSE THIRD_PARTY_NOTICES.md TEAM_INSTALLATION.md OPERATIONS.md API_GUIDE.md ./
COPY licenses/ ./licenses/
COPY scripts/audit_pdf_dependencies.py ./scripts/audit_pdf_dependencies.py
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
