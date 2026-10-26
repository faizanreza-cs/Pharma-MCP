PY ?= .venv/bin/python

.PHONY: setup test lint run http inspect docker

setup:
	uv sync --locked --extra dev

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m mypy

run:              ## stdio server (what desktop assistants launch)
	.venv/bin/pharma-mcp

http:             ## streamable HTTP on http://127.0.0.1:8000/mcp
	.venv/bin/pharma-mcp --transport streamable-http --port 8000

inspect:          ## open the MCP Inspector against the stdio server (needs Node)
	npx @modelcontextprotocol/inspector .venv/bin/pharma-mcp

docker:
	docker build -t pharma-mcp .
