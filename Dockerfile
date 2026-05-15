FROM python:3.12-slim

LABEL org.fuxi.version=1.0.0
LABEL org.fuxi.description=FuXi Unified Memory and Cognitive Engine System

RUN apt-get update && apt-get install -y --no-install-recommends curl && apt-get clean

WORKDIR /app

COPY pyproject.toml .
COPY fuxi/ ./fuxi/
COPY tests/ ./tests/
RUN pip install --no-cache-dir .

ENV FUXI_HOST=0.0.0.0
ENV FUXI_PORT=19528
ENV FUXI_BASE=/data
ENV FUXI_LOG_LEVEL=INFO
ENV FUXI_LOG_FORMAT=json

RUN mkdir -p /data/backups

VOLUME ["/data"]

EXPOSE 19528

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:19528/health || exit 1

CMD ["uvicorn", "fuxi.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "19528", "--workers", "2"]
