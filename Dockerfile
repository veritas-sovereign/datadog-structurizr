# syntax=docker/dockerfile:1.7
# datadog-structurizr without renderers: it writes the DSL and Mermaid sources.
# Validate or view them with the structurizr/structurizr image.

# Base image pinned by digest (multi-arch index), the same as drawio-structurizr;
# Dependabot proposes updates.
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

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
