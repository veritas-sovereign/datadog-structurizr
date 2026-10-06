# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The short or common-word name hints (`db`, `redis`, `mongo`, `mongodb`, `oracle`, `s3`, `sqs`, `sns`, `segment`) match only a whole token of the name. They matched anywhere, so `redistribution-svc` became a Redis datastore, `transactions3` an S3 external system, and `user-segments-api` an external Segment system even when its span type said it was a service. Dependencies whose names contained one of these hints inside a longer word can now be classified differently; use `[classify]` to keep the old group. `mongodb` is a hint of its own, so `mongodb-orders` is still a datastore.
- The README marks structurizr-cli as legacy and points to the `export` command of the `structurizr/structurizr` image.

## [0.2.0] - 2026-10-06

### Added

- `--no-raw`: draw the diagrams without saving the Datadog responses to `raw/`, where they must not be stored.
- Each dependency and included service has a `Classified by` property in `datadog-model.dsl` that names the rule that placed it: a `[classify]` pattern, its span type, a name hint, or none.

### Changed

- Python 3.10 or later is required. Python 3.9 reached end of life in October 2025.
- The README's Limitations section lists what Datadog data establishes and what it does not, such as the system boundary or the absence of a call.
- CI runs `ruff check` and `pyright`; both are in the `dev` extra.

### Fixed

- Services whose names make the same identifier (`cart-service`, `cart.service`, `cart_service`) were drawn as one element with the relationships of all of them. A service named `user`, or `<system>_system`, was merged into the person or the system the same way. Each name now gets its own element: the first keeps the identifier, later ones get `_2`, `_3`, and the run prints a warning. Components are handled the same way.

## [0.1.0] - 2026-10-06

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
- `Dockerfile`: an image with the tool and no renderers, on a base image pinned by digest, running as a non-root user. CI builds it and runs the example offline in it, and release tags publish it to `ghcr.io/veritas-sovereign/datadog-structurizr` for amd64 and arm64.
- Span aggregate responses are read in the shape the live API returns (`data[].attributes.by` and `attributes.compute`); a response in any other shape stops the run instead of being read as empty. Checked against a live Datadog account.
- `.env` is read from the current directory only. Before, an editable install also found the repository's `.env` by searching upwards from the package folder.
- L2 grouping, from a live service: probe paths are also dropped when the last segment ends in `health` or any segment is `actuator`; static files go into one `Static content` component; methods with no route go into one `Unrouted HTTP` component instead of one component each; `[components] strip_prefixes` removes a shared context path before grouping.
- A 429 from Datadog is retried up to 2 times after the wait given in `x-ratelimit-reset` (at most 60 seconds); other failures still stop the run at once.
- Dependencies are classified by the span type Datadog records on their own spans, fetched in one spans aggregate grouped by service and then type and saved as `raw/types.json`. Datastore types (`sql`, `redis`, `valkey`, `elasticsearch`, `opensearch`, `dynamodb`, `mongodb`, `cosmosdb`) make a database container with the type as its technology; service types (`web`, `http`, `rpc`, `soap`, `serverless`) override the datastore name hints. `[classify]` still wins, and names decide when there is no known type. `--offline` without `raw/types.json` classifies by name.
- `DD_SITE` (and `site` in the config file) accepts the forms copied from a browser or the API docs: `https://`, `api.` or `app.` and a trailing `/` are removed. Before, `api.datadoghq.com` made every call fail with 401.
- The README documents exporting PlantUML or Mermaid with the `structurizr/structurizr` image, which replaces the end-of-life structurizr-cli; CI checks the documented command writes all three views.
- `examples/checkout-web/`: a `c4.toml` and saved responses for a web service and its worker.

[Unreleased]: https://github.com/veritas-sovereign/datadog-structurizr/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/veritas-sovereign/datadog-structurizr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/veritas-sovereign/datadog-structurizr/releases/tag/v0.1.0
