<div align="center">

# datadog-structurizr

### Generate C4 diagrams of a Datadog APM service as Structurizr DSL and Mermaid

<br>

[![Full documentation](https://img.shields.io/badge/📖_full_documentation-github.com%2Fveritas--sovereign%2Fdatadog--structurizr-2f7ed8?style=for-the-badge&labelColor=555555)](https://github.com/veritas-sovereign/datadog-structurizr#readme)

<br>

🚀 [Quick Start](#quick-start) · 📦 [PyPI](https://pypi.org/project/datadog-structurizr/) · 🔑 [Datadog Access](#datadog-access) · 📋 [Mapping Conventions](#mapping-conventions) · ⚠️ [Limitations](#limitations) · 🧪 [Examples](examples/README.md) · 📝 [Changelog](CHANGELOG.md)

<br>

[![PyPI](https://img.shields.io/pypi/v/datadog-structurizr?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/datadog-structurizr/)
[![License: MIT](https://img.shields.io/badge/License-MIT-c9a227)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab?logo=python&logoColor=white)](pyproject.toml)
[![Input](https://img.shields.io/badge/Input-Datadog%20APM-632ca6?logo=datadog&logoColor=white)](https://docs.datadoghq.com/tracing/)
[![Output](https://img.shields.io/badge/Output-Structurizr%20DSL-438dd5)](https://docs.structurizr.com/dsl)
[![Output](https://img.shields.io/badge/Output-Mermaid%20C4-ff3670?logo=mermaid&logoColor=white)](https://mermaid.js.org/syntax/c4.html)
[![Tests](https://github.com/veritas-sovereign/datadog-structurizr/actions/workflows/test.yml/badge.svg)](https://github.com/veritas-sovereign/datadog-structurizr/actions/workflows/test.yml)
[![Last commit](https://img.shields.io/github/last-commit/veritas-sovereign/datadog-structurizr)](https://github.com/veritas-sovereign/datadog-structurizr/commits)

</div>

---

## Overview

`datadog-structurizr` reads one service's topology from Datadog APM and writes three C4 views of it:

| Here | C4 model | C4 view | Shows | Built from |
| --- | --- | --- | --- | --- |
| L0 | Level 1 | System Context | the user, the software system containing the service, the services it calls and is called by | service dependencies |
| L1 | Level 2 | Container | the service, the other services you name as part of the system, and their datastores inside the system boundary, with the neighbouring systems | service dependencies |
| L2 | Level 3 | Component | the service's entry points: HTTP endpoint groups and handlers | span resources |

The [C4 model](https://c4model.com/) numbers these views 1, 2 and 3. This project names them L0, L1 and L2, as do the view names and file names it writes.

L2 shows the API surface that APM sees, not the code structure behind it. Treat its components as a first draft of the service's entry points, not as its controllers, services and repositories.

Each run writes:

- a [Structurizr DSL](https://docs.structurizr.com/dsl) workspace with all three views. The generated model and views go into two files that every run rewrites; `workspace.dsl` includes them, is created once, and is yours to edit
- one [Mermaid C4](https://mermaid.js.org/syntax/c4.html) diagram per view, which renders on GitHub and in VS Code, and as SVG with `mmdc`
- the raw Datadog responses, so you can generate the diagrams again with `--offline` and no API calls

It is meant as a starting point for architecture documentation. Keep `workspace.dsl` as the source you maintain, and run the tool again whenever the services change: your edits survive.

## Quick Start

With Python (3.9 or later):

```bash
pip install datadog-structurizr
export DD_API_KEY=... DD_APP_KEY=... DD_SITE=datadoghq.com
datadog-structurizr --service checkout-web --env prod
```

For a web component made of several services, name the system and the other services in it:

```bash
datadog-structurizr --service checkout-web --env prod --system-name Checkout --include checkout-worker
```

To try it without Datadog keys, download [`examples/checkout-web/`](examples/checkout-web) and run, from inside that folder:

```bash
datadog-structurizr -c c4.toml --offline -o .
```

Open the output folder in [Structurizr local](#viewing-locally), paste `workspace-inline.dsl` (one file, nothing to include) into the [Structurizr playground](https://playground.structurizr.com), or open the `.mmd` files in any Mermaid viewer.

## Installation

Pick one:

| Option | Best for | You need |
| --- | --- | --- |
| [PyPI](#from-pypi) | everyday use | Python 3.9+; optionally `mmdc` (Node.js) to render SVGs |
| [From source](#from-source) | changing the tool or running its tests | Python 3.9+, git |
| [Docker](#docker) | running without Python | Docker; build the image yourself for now |

You also need a Datadog API key and application key. See [Datadog access](#datadog-access).

### From PyPI

[`datadog-structurizr`](https://pypi.org/project/datadog-structurizr/) is published to PyPI for every release.

```bash
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install datadog-structurizr                         # latest release
pip install datadog-structurizr==0.1.0                  # or a specific version
datadog-structurizr --help
```

To render the diagrams as SVG, also install the Mermaid CLI:

```bash
npm install -g @mermaid-js/mermaid-cli
```

### From source

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/veritas-sovereign/datadog-structurizr.git
   cd datadog-structurizr
   ```

2. Create and activate a virtual environment. `.venv/` is already git-ignored.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```

3. Install the package in editable mode. Add `[dev]` to also install pytest.

   ```bash
   pip install -e .                   # or: pip install -e '.[dev]'
   ```

4. Check the install:

   ```bash
   datadog-structurizr --version
   ```

To use the code without installing it, run `pip install -r requirements.txt` and prefix commands with `PYTHONPATH=src`.

### Docker

The [`Dockerfile`](Dockerfile) builds an image with the tool and no renderers. It is not published yet; CI builds and tests it on every change. Build it from a clone:

```bash
docker build -t datadog-structurizr .
```

Run it in the folder that holds `c4.toml`. `--user` makes the output files yours, and the keys come from the environment:

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  -e DD_API_KEY -e DD_APP_KEY \
  datadog-structurizr -c c4.toml -o . --no-render
```

The image has no `mmdc` or structurizr-cli, so use `--no-render`, and [view](#viewing-locally) or validate the output with the `structurizr/structurizr` image.

## Usage

### Generate the diagrams

```bash
datadog-structurizr [-c c4.toml] [--service NAME] [--env ENV] [--hours N] [-o DIR]
                    [--system-name NAME] [--include SERVICE[,SERVICE]]... [--no-person]
                    [--offline] [--no-render] [--no-input]
```

| Option | Meaning |
| --- | --- |
| `-c`, `--config` | [config file](#config-file) with the service, system boundary, classification and person |
| `--service` | APM service name |
| `--env` | APM environment, such as `prod`. The dependencies API requires it |
| `--hours` | lookback window in hours for dependencies and span resources (default 24) |
| `-o`, `--output` | output directory (default `output`) |
| `--system-name` | name of the software system (default: the service name) |
| `--include` | other APM services that are containers of the same system. Comma-separated, and repeatable. Adds to `include` in the config file |
| `--no-person` | draw no person; for services only called by other services |
| `--offline` | rebuild from `<output>/raw/*.json` instead of calling Datadog; no keys needed |
| `--no-render` | write `.dsl` and `.mmd` sources only; do not render images |
| `--no-input` | never prompt (see [Prompts](#prompts)) |
| `--version` | print the version |

### What to tell the tool

Only the service and environment are required. The other inputs fix the cases where Datadog data alone gives the wrong picture:

| Input | Why you would set it | Flag | Config file |
| --- | --- | --- | --- |
| Service and environment | required | `--service`, `--env` | `service`, `env` |
| Other services in the same system | A web component is often several services (web, BFF, worker). Without this, each one is drawn as a separate system and the container view is almost empty | `--include` | `[system] include` |
| System name | The system is usually called something other than its main service, for example `Checkout` rather than `checkout-web` | `--system-name` | `[system] name`, `description` |
| Classification | A dependency whose name does not match the [name hints](#elements) ends up in the wrong group | — | `[classify] datastores`, `external`, `internal` |
| Services to leave out | Telemetry collectors, agents and sidecars clutter every view | — | `ignore` |
| The person | The default `User` is generic. Name the real user, or turn the person off for a service that is only called by other services | `--no-person` | `[person] enabled`, `name`, `description` |

### Config file

Keep the inputs in a TOML file next to the generated `workspace.dsl`, and commit it, so a later run gives the same diagrams. A complete example is [`examples/checkout-web/c4.toml`](examples/checkout-web/c4.toml):

```toml
service = "checkout-web"
env = "prod"
hours = 24
ignore = ["otel-collector", "datadog-agent*"]

[system]
name = "Checkout"
description = "Lets shoppers review their cart and pay."
include = ["checkout-worker"]

[person]
enabled = true
name = "Shopper"
description = "Buys products on the web shop."

[classify]
datastores = ["ledger"]
external = []
internal = []

[components]
max = 12
strip_prefixes = []
```

| Key | Type | Meaning |
| --- | --- | --- |
| `service`, `env` | string | APM service and environment |
| `hours` | integer | lookback window (default 24) |
| `site` | string | Datadog site (default `datadoghq.com`) |
| `output` | string | output directory (default `output`) |
| `ignore` | list | services left out of every view |
| `[system] name`, `description` | string | the software system's name and description |
| `[system] include` | list | other APM services that are containers of this system. Exact names; each one costs one more API call |
| `[person] enabled` | boolean | draw a person (default `true`) |
| `[person] name`, `description` | string | the person (default `User`) |
| `[classify] datastores`, `external`, `internal` | list | force a dependency into a group, overriding the name hints |
| `[components] max` | integer | most components shown in L2, the last being `Other` (default 12, at least 2) |
| `[components] strip_prefixes` | list | path prefixes removed before routes are grouped, such as an app's context path `"/shop"` |

`ignore` and the `[classify]` lists accept `fnmatch` patterns (`*`, `?`, `[abc]`) and ignore case. Top-level keys such as `ignore` must come before the first `[table]`, as TOML requires. Unknown keys and wrong types stop the run with an error naming the key, so a typo cannot be silently ignored. Datadog keys are refused in the config file.

### Environment

Datadog keys only come from the environment. Environment variables can also come from a `.env` file in the current directory. Copy [`.env.example`](.env.example) to start:

| Variable | Required | Meaning |
| --- | --- | --- |
| `DD_API_KEY` | yes, unless `--offline` | Datadog API key |
| `DD_APP_KEY` | yes, unless `--offline` | Datadog application key with `apm_read` |
| `DD_SITE` | no | Datadog site: `datadoghq.com` (default), `datadoghq.eu`, `us3.datadoghq.com`, `us5.datadoghq.com`, `ap1.datadoghq.com` |
| `DD_SERVICE` | no, if given elsewhere | APM service name |
| `DD_ENV` | no, if given elsewhere | APM environment |
| `DD_LOOKBACK_HOURS` | no | lookback window in hours (default 24) |
| `OUTPUT_DIR` | no | output directory (default `output`) |

`.env` and `.env.*` are git-ignored, except `.env.example`. Do not commit keys.

Where the settings come from, highest priority first:

1. command-line flags
2. the config file
3. environment variables and `.env`
4. defaults

### Prompts

If the service or environment is still missing after these, the tool asks for it, but only when it runs in a terminal. In CI, or with `--no-input`, it stops with an error listing what is missing. It never asks for keys.

### Outputs

```
output/
├── workspace.dsl            yours: created once, never overwritten; includes the two files below
├── datadog-model.dsl        generated elements and relationships; rewritten every run
├── datadog-views.dsl        generated L0-SystemContext, L1-Containers, L2-Components views; rewritten every run
├── workspace-inline.dsl     workspace.dsl with both files pasted in, for the Structurizr playground
├── L0-SystemContext.mmd     Mermaid C4Context
├── L1-Containers.mmd        Mermaid C4Container
├── L2-Components.mmd        Mermaid C4Component
├── *.svg                    rendered views, if mmdc is installed
├── plantuml/                PlantUML export and images, if structurizr-cli and plantuml are installed
└── raw/
    ├── dependencies.json              dependencies of the service
    ├── dependencies-<service>.json    dependencies of each included service
    ├── resources.json                 resource names and span counts
    └── definition.json                service definition, if the service has one
```

`raw/` is replaced as a whole, and only after every Datadog call of the run has succeeded. It never mixes responses from different runs, and a failed run leaves the previous one in place. Do not keep other files in it.

`raw/` holds your internal service and route names. Check it before you commit it anywhere public.

### Typical workflow

1. Copy [`examples/checkout-web/c4.toml`](examples/checkout-web/c4.toml), and set `service`, `env` and the system name.
2. Run against Datadog once: `datadog-structurizr -c c4.toml`.
3. Look at the SVGs. Add the services that belong to the system to `include`, move wrongly grouped dependencies with `[classify]`, and drop noise with `ignore`. Then run again with `--offline`, which makes no API calls. A service newly added to `include` needs one more online run, to fetch its dependencies.
4. Add to `workspace.dsl` the elements and relationships Datadog cannot see, such as which component calls which downstream service. Commit `c4.toml`, `workspace.dsl` and the two `datadog-*.dsl` files to your documentation repository. Later runs rewrite only the `datadog-*.dsl` files.
5. Validate it, so a hand-written relationship to a renamed element is caught:

   ```bash
   docker run --rm -v "$PWD/output:/usr/local/structurizr" structurizr/structurizr validate -workspace /usr/local/structurizr/workspace.dsl
   ```

   [`examples/github-actions/c4.yml`](examples/github-actions/c4.yml) does this in CI: pull requests rebuild the model from the committed `raw/` responses and validate it, and a manual or weekly run fetches fresh data with the Datadog keys from the repository secrets. Until the package is on PyPI, the example installs it from GitHub; pin a commit there rather than `main`.

### Rendering

| Renderer | Used when | Output |
| --- | --- | --- |
| [`mmdc`](https://github.com/mermaid-js/mermaid-cli) | on `PATH` | `L0-SystemContext.svg`, `L1-Containers.svg`, `L2-Components.svg` |
| [structurizr-cli](https://docs.structurizr.com/cli) + [PlantUML](https://plantuml.com/) | both on `PATH` | `plantuml/*.puml` and `plantuml/*.svg` |

When neither is installed, only the sources are written. The generated workspace sets no theme, so structurizr-cli needs no network access to read it.

### Viewing locally

[Structurizr local](https://docs.structurizr.com/local) serves the workspace in a browser, with a diagram editor for layout. It reads `workspace.dsl` from the mounted folder, so the `!include` files are found next to it:

```bash
docker run -it --rm -p 8080:8080 -v "$PWD/output:/usr/local/structurizr" structurizr/structurizr local
```

Then open http://localhost:8080. Structurizr Lite and the separate `structurizr/cli` image are end of life; the `structurizr/structurizr` image replaces both.

## Datadog access

### Endpoints

| API | Used for | If it fails |
| --- | --- | --- |
| [`GET /api/v1/service_dependencies/{service}`](https://docs.datadoghq.com/api/latest/service-dependencies/) | `calls` and `called_by` of the service and of each included service: L0 and L1 | the run stops |
| [`POST /api/v2/spans/analytics/aggregate`](https://docs.datadoghq.com/api/latest/spans/) grouped by `resource_name` | components: L2 | the run stops. L2 shows one placeholder component only when the call succeeds and finds no indexed spans |
| [`GET /api/v2/services/definitions/{service}`](https://docs.datadoghq.com/api/latest/service-definition/) | description, team and languages | 404 (no definition) is ignored; any other status stops the run |

When Datadog answers 429 (rate limited), the call is retried up to 2 times, each after the number of seconds Datadog gives in the `x-ratelimit-reset` header. A 429 without that header, or asking for more than 60 seconds, is not retried.

When a call fails, the run prints the HTTP status, the call and Datadog's message to stderr, exits with status 1, and writes no diagrams. A diagram drawn from partial data would look complete but be wrong.

### Keys and permissions

- The application key needs the `apm_read` permission. A read-only service account key is enough. The tool makes no write calls.
- `DD_SITE` must match your Datadog organisation's site, or every call returns 403.

### Limits

- The service dependencies endpoint is in public beta.
- Span aggregates only cover **indexed** spans (those kept by retention filters). The span counts on components show relative traffic, not total requests.
- Span aggregates were limited to 50 requests per 60 seconds when measured on a live account (the `x-ratelimit-*` response headers), and that allowance is shared with everything else in the organisation that queries spans. A run makes one or two of these requests. When it is used up, Datadog answers 429.
- Span aggregates return the **100** resource names with the most spans. Resources beyond those are not fetched and do not appear in L2, not even in `Other`. They are the least-used ones. The response has no cursor for the next page, so there is no way to fetch more.

## Mapping conventions

### Elements

Each dependency name is checked against these rules in order. The first rule that matches decides:

| Rule | C4 element | Where it appears |
| --- | --- | --- |
| the service itself, or a name in `include` | container in the target system | L0 (inside the system), L1, L2 (the service, as the boundary) |
| matches `ignore` | left out | — |
| matches `[classify] datastores` | database container inside the target system | L1 |
| matches `[classify] external` | external software system, shown in grey | L0, L1 |
| matches `[classify] internal` | internal software system | L0, L1 |
| name matches `DATASTORE_HINTS` (`postgres`, `redis`, `kafka`, a `db` token, ...) | database container inside the target system | L1 |
| name matches `EXTERNAL_HINTS` (`stripe`, `aws.`, `s3`, `twilio`, ...) | external software system, shown in grey | L0, L1 |
| any other service | internal software system | L0, L1 |

The hints are matched case-insensitively, and `db` must be a whole word, so `feedback-service` is not a datastore. The hint lists are in [`mapper.py`](src/datadog_structurizr/mapper.py). Use `[classify]` rather than editing them.

The person (`User` by default) uses the service over HTTPS. It appears in L0, L1 and L2 unless it is turned off.

A service that calls itself gets no relationship. Relationships between containers of the target system appear in L1 and are hidden in L0, where they are inside the system.

### Components

- HTTP resources such as `GET /api/v1/cart/{id}` are grouped by their first path segment after `api`, version segments (`v1`, `v2`), and ids. `GET /api/v1/cart/{id}` and `POST /api/v1/cart/items` both go into `Cart API`, with the technology `HTTP endpoint group`.
- Other resources, such as queue consumers and jobs, each become one component with the technology `Entry point`.
- Probe endpoints are dropped: paths whose last segment is `health` or ends in `health` (`vhealth`, `app-health`), `healthz`, `healthcheck`, `ready`, `readyz`, `live`, `livez`, `ping` or `metrics`, and any path with an `actuator` segment.
- Static files (`.js`, `.css`, `.html`, images, fonts, also pre-compressed as `.br` or `.gz`) go into one `Static content` component.
- A method with no route (`GET`, `POST`), which some tracers record when they cannot name the endpoint, goes into one `Unrouted HTTP` component.
- When every route starts with the same context path, such as `/shop/...`, they all land in one group. List that prefix in `[components] strip_prefixes` to group by the segment after it.
- Components are sorted by span count. At most 12 are shown, and the rest are combined into `Other`. Change the number with `[components] max`.
- The person calls each HTTP endpoint group. Without a person, the services that call the target service do. Entry points get no incoming relationship.
- Components are only built for the target service, not for included services. Run the tool again with an included service as `service` to get its components.

### Identifiers

Element identifiers are the names with every character other than a letter, digit or `_` replaced by `_`. The system's identifier is its name followed by `_system`. Component identifiers are prefixed with their container's identifier and `__`. Output is the same for the same input.

## Limitations

- **Names decide the element type** unless you classify them. Check L1, and use `[classify]` for anything in the wrong group.
- **No component-to-dependency relationships.** Datadog does not say which entry point calls which downstream service, so L2 shows no relationships from components to other services. Add them by hand in `workspace.dsl`.
- **Hand edits appear only in the Structurizr output.** The Mermaid diagrams are drawn from Datadog data alone.
- **Generated identifiers can change.** Hand-written relationships refer to generated identifiers such as `checkout_web__Cart_API`. If a service or route group is renamed or disappears, structurizr-cli reports the dangling identifier, and you fix `workspace.dsl` by hand.
- **One system per run.** Run the command once per system and merge the workspaces by hand if you need a landscape view.
- **Layout is automatic.** Structurizr views use `autoLayout`. Mermaid's C4 layout is basic; for presentation diagrams, use the Structurizr output.

## Examples

| Directory | What it shows |
| --- | --- |
| [`checkout-web/`](examples/checkout-web) | A `c4.toml` and saved responses for a web service and its worker: internal, datastore and external dependencies, two callers, route groups, a probe, a queue consumer, an ignored collector and a classified datastore |

See [`examples/README.md`](examples/README.md) for how to run it.

## Testing

```bash
pip install -e '.[dev]'
pytest
```

The tests replace the Datadog calls with fakes, so they need no keys or network access. They run `examples/checkout-web/` end to end and cover configuration, the client, the mapper and the emitter.

## Project structure

```
datadog-structurizr/
├── src/
│   └── datadog_structurizr/     Python package
│       ├── __init__.py          package version
│       ├── main.py              datadog-structurizr command
│       ├── config.py            settings from the command line, config file, environment and .env
│       ├── client.py            Datadog API calls; saves and replays raw responses
│       ├── model.py             C4 model classes
│       ├── mapper.py            maps Datadog data onto the C4 model
│       ├── emitter.py           writes Structurizr DSL and Mermaid C4
│       └── render.py            optional rendering with mmdc, or structurizr-cli and plantuml
├── examples/
│   ├── README.md                how to run the sample
│   ├── checkout-web/            sample c4.toml and saved Datadog responses
│   └── github-actions/c4.yml    example workflow: rebuild, validate, refresh from Datadog
├── tests/
│   ├── conftest.py              clean environment and shared settings
│   ├── test_examples.py         end-to-end offline runs
│   ├── test_config.py           config file, precedence, prompts and errors
│   ├── test_client.py           request shapes, fallbacks and errors, with fake responses
│   ├── test_mapper.py           boundary, classification, ignore, person and components
│   └── test_emitter.py          DSL nesting and Mermaid views
├── .github/
│   ├── dependabot.yml           weekly updates for GitHub Actions and the Docker base image
│   └── workflows/
│       ├── test.yml             pytest on Python 3.9 and 3.13, Structurizr validation, Docker image build
│       └── publish-pypi.yml     builds the package; publishes it to PyPI on v* tags
├── Dockerfile                   image with the tool and no renderers; not published yet
├── .dockerignore
├── .env.example                 settings template
├── pyproject.toml               package metadata and datadog-structurizr command
├── requirements.txt             runtime dependencies
├── CHANGELOG.md
├── LICENSE
├── .editorconfig
├── .gitattributes
└── .gitignore
```

The package lives under `src/` so it can only be imported once installed, and so it is not mistaken for a second copy of the repository folder.

### How a run works

```
Datadog ──► client.py ──► mapper.py ──► emitter.py ──► datadog-*.dsl, *.mmd ──► render.py (optional)
            fetch,         dependencies    DSL and                                mmdc, structurizr-cli
            save raw/      and resources   Mermaid text
                           to C4 model
```

## Naming conventions

- **Repository, distribution and command:** `datadog-structurizr` (kebab-case)
- **Python package:** `datadog_structurizr` (snake_case), in `src/`
- **Modules:** short snake_case nouns, without a `datadog_` prefix, since the package name already provides it
- **Views:** `L0-SystemContext`, `L1-Containers`, `L2-Components`, both as Structurizr view keys and as file names
- **C4 terms:** element, relationship, software system, container, component, person

## Related

[drawio-structurizr](https://github.com/veritas-sovereign/drawio-structurizr) converts C4 diagrams drawn in draw.io into Structurizr DSL. Use it for the parts of the architecture that Datadog does not trace.

## Contributing

Issues and pull requests are welcome at [veritas-sovereign/datadog-structurizr](https://github.com/veritas-sovereign/datadog-structurizr). Run `pytest` before opening a pull request (GitHub Actions runs it too), and add saved responses to `examples/` when you change how Datadog data is read.

## License

Released under the [MIT License](LICENSE).
