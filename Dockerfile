# syntax=docker/dockerfile:1
FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml /opt/
COPY spectre_utils/ /opt/spectre_utils
RUN uv pip install --system --no-cache -r /opt/pyproject.toml
FROM python:3.11-slim AS runtime
ENV PYTHONPATH="/opt"
COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /opt /opt
