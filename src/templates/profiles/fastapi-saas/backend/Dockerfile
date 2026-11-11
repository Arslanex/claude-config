FROM python:3.12-slim AS builder
# Tedarik zinciri: uv surumu sabit; yukseltme bilincli yapilir.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations

FROM python:3.12-slim
RUN useradd --create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/migrations /app/migrations
ENV PATH="/app/.venv/bin:$PATH"
USER app
CMD ["python", "-c", "print('komut compose tarafindan verilir')"]
