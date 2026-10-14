FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
COPY pyproject.toml README.md LICENSE ./
COPY pharma_mcp ./pharma_mcp
RUN uv pip install --system --no-cache .
EXPOSE 8000
# stdio by default; for HTTP: docker run -p 8000:8000 pharma-mcp pharma-mcp --transport streamable-http --host 0.0.0.0
ENTRYPOINT []
CMD ["pharma-mcp"]
