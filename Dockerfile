FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev --no-editable

USER 1000:1000

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000 8443

CMD ["uvicorn", "octw.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
