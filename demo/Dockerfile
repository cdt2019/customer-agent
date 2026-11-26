# 模拟店铺（代替接入方），连同聊天窗的 widget.js。在仓库根目录构建：docker build -f demo/Dockerfile .
# widget/dist 要先在本机 pnpm build 好。
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
ENV UV_CACHE_DIR=/tmp/uv-cache UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUTF8=1 PATH=/app/.venv/bin:$PATH

WORKDIR /app/demo
COPY demo/pyproject.toml demo/uv.lock ./
RUN --mount=type=cache,target=/tmp/uv-cache uv sync --locked --no-dev --no-install-project
COPY demo/ ./
RUN --mount=type=cache,target=/tmp/uv-cache uv sync --locked --no-dev
COPY widget/dist /app/widget/dist

ENV DATA_DIR=/app/demo/data WIDGET_DIR=/app/widget/dist
RUN useradd --uid 10001 --no-create-home shop
USER shop
EXPOSE 8100
CMD ["demo-shop", "serve", "--host", "0.0.0.0", "--port", "8100"]
