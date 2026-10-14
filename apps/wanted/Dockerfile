# One service: the web page + JSON API on $PORT (default 8080). Built from the ROOT of the Knos monorepo, so the app
# and the Knos it locks pre-orders with are the same commit:
#   docker build -f apps/wanted/Dockerfile -t knos-wanted . && docker run -p 8080:8080 --env-file apps/wanted/.env knos-wanted
# Without any env var it runs on MOCK (synthetic) Qloo data and the escrow buttons say what is missing.
FROM python:3.12-slim
WORKDIR /src
COPY pyproject.toml README.md README.pypi.md LICENSE ./
COPY src ./src
COPY terms ./terms
COPY config/fees.yaml ./config/fees.yaml
COPY apps/wanted ./apps/wanted
RUN pip install --no-cache-dir . "./apps/wanted[escrow]"
WORKDIR /app
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
ENV HOST=0.0.0.0 PORT=8080 KNOS_WANTED_CACHE=/data/qloo KNOS_WANTED_STATE=/data/state KNOS_CLUSTER=devnet
EXPOSE 8080
CMD ["python", "-m", "knos_wanted", "serve"]
