# Container image for CoWastewaterBot — run the MCP server or CLI with only
# Docker installed (no local Python / uv needed).
#
# Build:  docker build -t cowastewaterbot .
# MCP:    docker run -i --rm cowastewaterbot            # stdio MCP server (default)
# CLI:    docker run --rm cowastewaterbot cowastewater sites
#
# The published image (ghcr.io/<owner>/cowastewaterbot) is built by
# .github/workflows/docker-publish.yml, so you can `docker run` it without
# building anything yourself.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Bytecode-compile on install and copy (not hardlink) into the image layer.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1

WORKDIR /app

# Hatchling reads README.md (project.readme); the package lives under src/.
COPY pyproject.toml README.md ./
COPY src ./src

# Install runtime deps + the package into /app/.venv. No dev extras in the image.
RUN uv sync --no-dev

# Default: serve the MCP server over stdio. `uv run --no-sync` reuses the venv
# built above instead of re-resolving at container start. Override the command
# (e.g. `... cowastewater sites`) to run the CLI instead.
ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["cowastewater-mcp"]
