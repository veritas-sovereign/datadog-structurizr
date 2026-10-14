# syntax=docker/dockerfile:1.7
# datadog-structurizr without renderers: it writes the DSL and Mermaid sources.
# Validate or view them with the structurizr/structurizr image.

# Base image pinned by digest (multi-arch index), the same as drawio-structurizr;
# Dependabot proposes updates.
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install . && rm -rf /src

RUN useradd --create-home --uid 10001 app
USER app

WORKDIR /work
ENTRYPOINT ["datadog-structurizr"]
CMD ["--help"]
