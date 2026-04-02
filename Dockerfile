FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY alembic.ini alembic/versions/ ./

CMD ["uv", "run", "langrove", "serve", "--host", "0.0.0.0", "--port", "8123"]
