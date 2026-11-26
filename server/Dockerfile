# 客服服务。在仓库根目录构建：docker build -f server/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
ENV UV_CACHE_DIR=/tmp/uv-cache UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUTF8=1 PATH=/app/.venv/bin:$PATH

WORKDIR /app/server
# 先装依赖再拷代码：改代码不用重装 torch
COPY server/pyproject.toml server/uv.lock ./
RUN --mount=type=cache,target=/tmp/uv-cache uv sync --locked --no-dev --no-install-project
COPY server/ ./
RUN --mount=type=cache,target=/tmp/uv-cache uv sync --locked --no-dev
COPY evals /app/evals

# 模型、Docling 的模型、上传的文件都放在挂进来的 /data
ENV MODELS_DIR=/data/models HF_HOME=/data/hf UPLOADS_DIR=/data/uploads IMAGES_DIR=/data/images EVALS_DIR=/app/evals
RUN useradd --uid 10001 --no-create-home agent && mkdir -p /data && chown agent /data
USER agent
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn customer_agent.api:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
