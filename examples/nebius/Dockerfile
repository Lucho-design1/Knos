# Knos builds Knos on Nemotron: the demo + its panel, for a Nebius Serverless Endpoint (container port 8080).
# Build from the repository root:  docker build -f examples/nebius/Dockerfile -t knos-nebius .
# At start it runs the golden path once (live when NEBIUS_API_KEY / TAVILY_API_KEY are set in the container's
# environment, MOCK otherwise, labelled on the page), then serves /out/panel.html. No key is baked into the image.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /knos
COPY . /knos
RUN pip install --no-cache-dir -e .
EXPOSE 8080
CMD ["sh", "-c", "mkdir -p /out; python -m knos.nebius demo --root /knos --out /out --iterations ${KNOS_DEMO_ITERATIONS:-4} > /out.log 2>&1; cp /out.log /out/demo-output.txt; cp /out/panel.html /out/index.html; exec python -m http.server 8080 --directory /out"]
