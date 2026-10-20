# syntax=docker/dockerfile:1.7
# datadog-structurizr without renderers: it writes the DSL and Mermaid sources.
# Validate or view them with the structurizr/structurizr image.

# Base image pinned by digest (multi-arch index), the same as drawio-structurizr;
# Dependabot proposes updates.
FROM python:3.15-slim-bookworm@sha256:2a41267d9de9d358f77a1de356e0f16ecba8d39827855be0ce9ef4792edce402

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
