# syntax=docker/dockerfile:1
FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml spectre_utils /opt
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /opt/ &&\
    uv sync --no-install-project --no-dev
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /opt/ &&\
    uv sync --frozen --no-dev
FROM python:3.11-slim AS runtime
ENV PATH="/opt/.venv/bin:$PATH"
COPY --from=build /opt /opt
