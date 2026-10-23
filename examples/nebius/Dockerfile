# Knos on Nemotron for a Nebius Serverless Endpoint (container port 8080).
# Build from the repository root:  docker build -f examples/nebius/Dockerfile -t knos-nebius .
# At start it runs the one flow (post -> agent codes on Nemotron -> referee -> paid in LiteSVM -> metered) and the
# "Knos builds Knos" demo once, live when NEBIUS_API_KEY / TAVILY_API_KEY are set in the container's environment, MOCK
# otherwise (labelled on the pages), then serves /out: index.html is the flow, panel.html the demo, devnet-run.html the
# committed devnet run. No key and no wallet is baked into the image (the container holds no devnet money).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /knos
COPY . /knos
RUN pip install --no-cache-dir -e . pytest
EXPOSE 8080
CMD ["sh", "-c", "mkdir -p /out; python -m knos.nebius flow --root /knos --out /out/flow > /out/flow.log 2>&1; python -m knos.nebius demo --root /knos --out /out --iterations ${KNOS_DEMO_ITERATIONS:-4} > /out.log 2>&1; cp /out.log /out/demo-output.txt; cp /out/flow/flow.html /out/index.html; cp /knos/examples/nebius/flow-run/flow.html /out/devnet-run.html; exec python -m http.server 8080 --directory /out"]
