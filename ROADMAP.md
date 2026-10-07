# Roadmap

datadog-structurizr turns what Datadog APM observed about one service into C4 views. The items below came up in reviews. None is scheduled: each waits for the condition under "Starts when", so the tool does not grow features nobody uses.

## Planned when needed

### Expected calls that were not observed

You declare the calls you expect, and each run reports the ones Datadog did not record in the window:

```toml
[expect]
calls = ["checkout-web -> cart-service", "checkout-web -> stripe-api"]
```

An expected call that was not seen is printed as a warning (`expected call checkout-web -> stripe-api not observed in the last 24h`), drawn as a dashed relationship tagged `Not observed`, and marked `"observed": false` in `c4-model.json`. The wording is always "not observed in the window", never "missing": as [Limitations](README.md#limitations) says, a call not seen in the window may still exist. A `--fail-on-unobserved` exit code could let CI act on it.

**Starts when:** someone keeps an expected architecture and wants to see where Datadog disagrees with it.

## Future, not planned

These are left out on purpose. Each lists what would have to change before it is reconsidered.

### Confidence scores

A number such as "0.8 likely a datastore" would need labelled data to be calibrated against, and there is none, so the number would be made up. The `Classified by` property and `classified_by` in `c4-model.json` already say how strong the evidence is, in order: a `[classify]` pattern, then a span type, then a name hint, then nothing.

If a reader needs this as a field, an `evidence_strength` of `explicit`, `span_type`, `name_hint` or `none`, taken from `classified_by`, gives it without inventing a number.

**Reconsider when:** there is a set of a few hundred dependencies classified by hand to measure the rules against.

### Pydantic

The model is a few small dataclasses, and `config.py` already checks the config file. Pydantic would add a large dependency to a command whose runtime dependencies are `requests` and `python-dotenv`.

**Reconsider when:** the tool reads models from outside, for example a `c4-model.json` merged back in. Even then, validating against `schema/c4-model.schema.json` is likely enough.

### Graph database

The tool covers one service per run and keeps no state between runs. A graph database means state across runs, a server to operate and a way to reconcile what each run saw: a different product.

**Reconsider when:** several teams need the topology of many services in one place. That belongs in a separate project that reads the `c4-model.json` of each service and merges them; this repository stays the producer of that file.
