"""--json: the model and its evidence as c4-model.json, against the schema in schema/."""
import json
from pathlib import Path

import jsonschema

from datadog_structurizr.emitter import JSON_FILE, SCHEMA_VERSION
from datadog_structurizr.main import main

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema" / "c4-model.schema.json").read_text())
GOLDEN = Path(__file__).parent / "golden" / "checkout-web.c4-model.json"


def _run(checkout_dir, *extra):
    rc = main(["--config", str(checkout_dir / "c4.toml"), "--offline", "-o", str(checkout_dir),
               "--no-render", "--json", *extra])
    assert rc == 0
    return json.loads((checkout_dir / JSON_FILE).read_text())


def _without_version(doc):
    return {**doc, "generator": {**doc["generator"], "version": "*"}}


def test_example_matches_the_golden_file(checkout_dir):
    # Regenerate after a deliberate change: run the example with --json and copy
    # c4-model.json here with the generator version set to "*".
    assert _without_version(_run(checkout_dir)) == json.loads(GOLDEN.read_text())


def test_output_matches_the_schema(checkout_dir):
    doc = _run(checkout_dir)
    jsonschema.validate(doc, SCHEMA)
    assert SCHEMA["properties"]["schema_version"]["const"] == SCHEMA_VERSION == doc["schema_version"]


def test_output_is_sorted_and_the_same_on_every_run(checkout_dir):
    doc = _run(checkout_dir)
    text = (checkout_dir / JSON_FILE).read_text()
    _run(checkout_dir)
    assert (checkout_dir / JSON_FILE).read_text() == text
    keys = [e["key"] for e in doc["elements"]]
    assert keys == sorted(keys)
    pairs = [(r["source"], r["target"]) for r in doc["relationships"]]
    assert pairs == sorted(pairs)


def test_every_relationship_and_parent_refers_to_an_element(checkout_dir):
    doc = _run(checkout_dir)
    keys = {e["key"] for e in doc["elements"]}
    assert all(e["parent"] in keys for e in doc["elements"] if e["parent"])
    assert all(r["source"] in keys and r["target"] in keys for r in doc["relationships"])


def test_evidence_names_the_datadog_call(checkout_dir):
    doc = _run(checkout_dir)
    rels = {(r["source"], r["target"]): r["evidence"] for r in doc["relationships"]}
    assert rels[("checkout_worker", "aws_sqs")] == [
        {"source": "GET /api/v1/service_dependencies/checkout-worker", "detail": "calls"}]
    assert rels[("api_gateway", "checkout_web")] == [
        {"source": "GET /api/v1/service_dependencies/checkout-web", "detail": "called_by"}]
    assert rels[("user", "checkout_web")] == [
        {"source": "assumption", "detail": "the person uses the target service"}]
    elements = {e["key"]: e for e in doc["elements"]}
    assert elements["redis"]["evidence"] == [
        {"source": "POST /api/v2/spans/analytics/aggregate by service and type", "detail": "span types redis 41000"},
        {"source": "GET /api/v1/service_dependencies/checkout-web", "detail": "calls"}]
    assert elements["checkout_web__Cart_API"]["evidence"] == [
        {"source": "POST /api/v2/spans/analytics/aggregate by resource_name of checkout-web",
         "detail": "2 resources, 13300 spans"}]
    assert elements["ledger"]["classified_by"] == "[classify] datastores pattern ledger"
    assert elements["user"]["classified_by"] is None


def test_no_json_without_the_flag(checkout_dir):
    main(["--config", str(checkout_dir / "c4.toml"), "--offline", "-o", str(checkout_dir), "--no-render"])
    assert not (checkout_dir / JSON_FILE).exists()


def test_no_raw_run_writes_json_with_the_same_kind_of_evidence(tmp_path, monkeypatch):
    from test_client import fake_datadog

    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    fake_datadog(monkeypatch)
    out = tmp_path / "o"
    rc = main(["--service", "web", "--env", "prod", "-o", str(out), "--no-render", "--no-input",
               "--no-raw", "--json"])
    assert rc == 0
    doc = json.loads((out / JSON_FILE).read_text())
    jsonschema.validate(doc, SCHEMA)
    assert not (out / "raw").exists()
    sources = {ev["source"] for item in doc["elements"] + doc["relationships"] for ev in item["evidence"]}
    assert "GET /api/v1/service_dependencies/web" in sources
    assert not any("raw/" in s or s.endswith(".json") for s in sources)
