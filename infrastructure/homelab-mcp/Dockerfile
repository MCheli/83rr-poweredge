# homelab-mcp: read-only claude.ai connector for the Seafile "AI Context" library.
# Built on the server from this repo (not published to GHCR, not watchtower-managed):
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml build homelab-mcp
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTMCP_HOME=/data

RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin mcp \
    && mkdir -p /data && chown mcp /data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ .

USER mcp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).read()"]
CMD ["python", "server.py"]
