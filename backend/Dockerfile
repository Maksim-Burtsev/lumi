FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

# Install the package itself
COPY . .
RUN uv pip install --system --no-deps -e .

EXPOSE 8000

CMD ["uvicorn", "lumi.main:app", "--host", "0.0.0.0", "--port", "8000"]
