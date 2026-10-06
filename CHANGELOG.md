# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `datadog-structurizr` command: reads one APM service from Datadog and writes C4 system context (L0), container (L1) and component (L2) views as a Structurizr DSL workspace and as Mermaid C4 diagrams.
- Dependencies from `GET /api/v1/service_dependencies/{service}` (`calls`, `called_by`). Datastore-like names become database containers inside the system, SaaS and cloud-API-like names become external systems, and every other service becomes an internal system.
- Components from `POST /api/v2/spans/analytics/aggregate` grouped by `resource_name`: HTTP routes are grouped by their first path segment, probe endpoints are dropped, and at most 12 components are kept (the rest go into `Other`). Server and consumer spans are tried first.
- Description, team and languages from `GET /api/v2/services/definitions/{service}` when the service has a definition.
- The Structurizr output is split so that hand edits survive a new run: `datadog-model.dsl` and `datadog-views.dsl` are rewritten on every run, and `workspace.dsl` includes them with `!include`. `workspace.dsl` is created only when it does not exist and is never overwritten. Its views use `include *`, so elements and relationships added there appear in the generated views. `workspace-inline.dsl` has the includes pasted in for the Structurizr playground.
- Raw API responses are saved to `<output>/raw/`, and `--offline` rebuilds from them without keys or network access. `raw/` is replaced as a whole once every call of the run has succeeded, so it never mixes responses from different runs and is never left half-written.
- Images are rendered with `mmdc` when it is installed, and through structurizr-cli and plantuml when both are installed. `--no-render` writes sources only.
- Inputs for what Datadog data alone gets wrong, from flags or a TOML file given with `-c/--config`:
  - `--include` / `[system] include`: other APM services that are containers of the same system. Their dependencies are fetched too and saved as `raw/dependencies-<service>.json`.
  - `--system-name` / `[system] name` and `description`.
  - `[classify] datastores`, `external` and `internal`: fnmatch patterns that override the name hints.
  - `ignore`: fnmatch patterns for services left out of every view.
  - `--no-person` / `[person] enabled`, `name` and `description`. Without a person, the services calling the target call its HTTP endpoint groups.
- Settings precedence: flags, then the config file, then environment variables and `.env`. Datadog keys are only read from the environment and are refused in the config file. Unknown config keys and wrong types stop the run.
- On a terminal, a missing service or environment is asked for. `--no-input` turns this off. Nothing is asked in CI.
- Failed Datadog calls stop the run with exit status 1, and no diagrams are written. Only a 404 from the service definition endpoint is accepted, since that means the service has no definition. The spans query without the `span.kind` filter is only sent when the filtered query succeeds with no results, never after a failed call.
- `[components] max` sets how many components L2 shows (default 12).
- L2 components are labelled for what APM sees: HTTP route groups have the technology `HTTP endpoint group`, other resources `Entry point`, and the L2 view description says they are entry points, not code structure.
- `examples/github-actions/c4.yml`: a workflow that rebuilds the model from committed `raw/` responses on pull requests and validates it with the `structurizr/structurizr` image, and fetches fresh data on a manual or weekly run. The README shows how to view the output with Structurizr local and validate it with Docker.
- `Dockerfile`: an image with the tool and no renderers, on a base image pinned by digest, running as a non-root user. CI builds it and runs the example offline in it; it is not published yet.
- `examples/checkout-web/`: a `c4.toml` and saved responses for a web service and its worker.
