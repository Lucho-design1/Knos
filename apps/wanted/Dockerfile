# Knos's demand check as one service: the web page + JSON API on $PORT (default 8080). Built from the ROOT of the Knos
# monorepo, so the app and the Knos it records and locks pre-orders with are the same commit:
#   docker build -f apps/wanted/Dockerfile -t knos-demand . && docker run -p 8080:8080 --env-file apps/wanted/.env knos-demand
# Qloo is reached only through `qloo mcp` (@qloo/qloo-harness, Node 22.19+) via the official MCP SDK. Without
# QLOO_API_KEY it runs on Knos's MOCK (synthetic) MCP server and every answer says so.
FROM node:22.19-bookworm-slim AS node

FROM python:3.12-slim
COPY --from=node /usr/local/ /usr/local/
RUN npm install --global --no-audit --no-fund @qloo/qloo-harness@0.1.26 && qloo --version
WORKDIR /src
COPY pyproject.toml README.md README.pypi.md LICENSE ./
COPY src ./src
COPY terms ./terms
COPY config/fees.yaml ./config/fees.yaml
COPY apps/wanted ./apps/wanted
RUN pip install --no-cache-dir . "./apps/wanted[escrow]" && sh apps/wanted/bridge/install.sh
WORKDIR /app
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
ENV HOST=0.0.0.0 PORT=8080 KNOS_WANTED_CACHE=/data/qloo-mcp KNOS_WANTED_STATE=/data/state KNOS_WANTED_RECORD=/data/record \
    PYTHONPATH=/src/apps/wanted KNOS_CLUSTER=devnet QLOO_BASE_URL=https://hackathon.api.qloo.com QLOO_TRUSTED_BASE_URL=https://hackathon.api.qloo.com
EXPOSE 8080
CMD ["python", "-m", "knos_wanted", "serve"]
