FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.14-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/adapters/models/bedrock.py ./src/adapters/models/bedrock.py
COPY src/apps/agentcore/main.py ./src/apps/agentcore/main.py
ENV PYTHONPATH=/app/src
USER 10001:10001
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "apps.agentcore.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
