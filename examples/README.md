# Examples

| Directory | What it shows |
| --- | --- |
| `checkout-web/` | `c4.toml` plus saved Datadog responses for `checkout-web`, a web service, and `checkout-worker`, a background worker in the same system. They call two internal services, Postgres, Redis, Stripe, SQS, a `ledger` service and an OpenTelemetry collector, and are called by an API gateway and a mobile BFF. The service serves cart and checkout routes, a health probe and a queue consumer. |

`c4.toml` shows every input: it names the system `Checkout` and the person `Shopper`, includes `checkout-worker` as a second container, classifies `ledger` as a datastore (its name matches no hint), and ignores `otel-collector`.

Run from inside `checkout-web/` after `pip install datadog-structurizr` (or `pip install -e ../..` from a checkout). No Datadog keys are needed:

```bash
cd checkout-web
datadog-structurizr -c c4.toml --offline -o .
```

To see what the inputs change, run it without the config file and compare the views:

```bash
datadog-structurizr --service checkout-web --env prod --offline -o .
```

Both write `workspace.dsl` (only if missing), `datadog-model.dsl`, `datadog-views.dsl`, `workspace-inline.dsl`, `L0-SystemContext.mmd`, `L1-Containers.mmd` and `L2-Components.mmd`, and an `.svg` for each view if `mmdc` is installed. Generated files are git-ignored. Only `c4.toml` and `raw/` are checked in.

To make your own sample, run once against Datadog and copy `<output>/raw/`. Check the copied files for internal service and route names before you commit them.
