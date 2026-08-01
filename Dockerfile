# SolarQuant edge plugin image. Build from the repo root:
#   docker build -t triage-plugin .
# The trained bundle bakes in; MODEL_PATH + a mount can override it.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
# deps first, project second: a source edit re-runs only the cheap layer
RUN uv sync --frozen --no-dev --extra plugin --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra plugin
COPY model/model.joblib ./model/model.joblib
ENV PATH="/app/.venv/bin:$PATH" DB_PATH=/data/triage.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "triage.plugin.app:app", "--host", "0.0.0.0", "--port", "8000"]
