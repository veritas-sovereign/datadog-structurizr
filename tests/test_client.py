"""Datadog calls with requests replaced by fakes; nothing goes over the network."""
import json
from dataclasses import replace

import pytest

from datadog_structurizr import client


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)
        self.headers = headers or {}

    def json(self):
        return self._body


def bucket(by, count):
    """One bucket as the live spans aggregate API returns it."""
    return {"type": "bucket", "id": "b", "attributes": {"by": by, "compute": {"c0": count}}}


def test_resources_parse_live_response_shape(monkeypatch, online_cfg):
    live = {"data": [bucket({"resource_name": "GET /api/v1/cart/{id}"}, 1200),
                     bucket({"resource_name": "POST"}, 300)],
            "meta": {"elapsed": 100, "status": "done", "traffic_type": "sampled"}}
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: FakeResponse(200, live))
    assert client.fetch_resources(online_cfg) == [
        {"resource": "GET /api/v1/cart/{id}", "hits": 1200}, {"resource": "POST", "hits": 300}]


def test_resources_unexpected_shape_raises(monkeypatch, online_cfg):
    old_shape = {"data": {"buckets": [{"by": {"resource_name": "GET /cart"}, "computes": {"c0": 7}}]}}
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: FakeResponse(200, old_shape))
    with pytest.raises(client.DatadogAPIError, match="expected a list"):
        client.fetch_resources(online_cfg)


def test_dependencies_without_called_by(monkeypatch, online_cfg):
    # The live API leaves out called_by when nothing calls the service.
    monkeypatch.setattr(client.requests, "get",
                        lambda *a, **k: FakeResponse(200, {"name": "checkout-web", "calls": ["redis"]}))
    assert client.fetch_service_dependencies(online_cfg) == {"name": "checkout-web", "calls": ["redis"]}


def test_dependencies_request(monkeypatch, online_cfg):
    seen = {}

    def fake_get(url, headers, params, timeout):
        seen.update(url=url, headers=headers, params=params)
        return FakeResponse(200, {"name": "checkout-web", "calls": ["a"], "called_by": []})

    monkeypatch.setattr(client.requests, "get", fake_get)
    deps = client.fetch_service_dependencies(online_cfg)
    assert deps["calls"] == ["a"]
    assert seen["url"] == "https://api.datadoghq.com/api/v1/service_dependencies/checkout-web"
    assert seen["params"]["env"] == "prod"
    assert seen["params"]["end"] - seen["params"]["start"] == 24 * 3600
    assert seen["headers"]["DD-API-KEY"] == "k"


def test_dependencies_error_raises(monkeypatch, online_cfg):
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: FakeResponse(403, {"errors": ["Forbidden"]}))
    with pytest.raises(RuntimeError, match="403"):
        client.fetch_service_dependencies(online_cfg)


def test_resources_fall_back_when_span_kind_unset(monkeypatch, online_cfg):
    queries = []

    def fake_post(url, headers, json, timeout):
        query = json["data"]["attributes"]["filter"]["query"]
        queries.append(query)
        if "span.kind" in query:
            return FakeResponse(200, {"data": [], "meta": {"status": "done"}})
        return FakeResponse(200, {"data": [
            bucket({"resource_name": "GET /cart"}, 7),
            bucket({}, 1),
        ], "meta": {"status": "done"}})

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.fetch_resources(online_cfg) == [{"resource": "GET /cart", "hits": 7}]
    assert queries == ["service:checkout-web env:prod @span.kind:(server OR consumer)",
                       "service:checkout-web env:prod"]


def test_resources_error_raises_without_fallback(monkeypatch, online_cfg):
    queries = []

    def fake_post(url, headers, json, timeout):
        queries.append(json["data"]["attributes"]["filter"]["query"])
        return FakeResponse(503, {"errors": ["Service unavailable"]})

    monkeypatch.setattr(client.requests, "post", fake_post)
    with pytest.raises(client.DatadogAPIError, match="503"):
        client.fetch_resources(online_cfg)
    # The unfiltered query would count client spans as components.
    assert len(queries) == 1
    assert not (online_cfg.raw_dir / "resources.json").exists()


def test_definition_is_optional(monkeypatch, online_cfg):
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: FakeResponse(404, {}))
    assert client.fetch_service_definition(online_cfg) == {}


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_definition_error_other_than_404_raises(monkeypatch, online_cfg, status):
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: FakeResponse(status, {}))
    with pytest.raises(client.DatadogAPIError, match=str(status)):
        client.fetch_service_definition(online_cfg)


def test_offline_reads_raw_files(offline_cfg):
    assert client.fetch_service_dependencies(offline_cfg)["name"] == "checkout-web"
    assert client.fetch_resources(offline_cfg)


def fake_datadog(monkeypatch, definition_status=200, spans_status=200):
    """Answer every call of one run; returns the list of URLs called."""
    urls = []

    def fake_get(url, headers, timeout, params=None):
        urls.append(url)
        if "/definitions/" in url:
            return FakeResponse(definition_status, {"data": {"attributes": {"schema": {}}}})
        return FakeResponse(200, {"name": url.rsplit("/", 1)[-1], "calls": [], "called_by": []})

    def fake_post(url, headers, json, timeout):
        urls.append(url)
        return FakeResponse(spans_status, {"data": [bucket({"resource_name": "GET /cart"}, 7)]})

    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client.requests, "post", fake_post)
    return urls


def test_fetch_all_saves_every_response(monkeypatch, online_cfg):
    online_cfg = replace(online_cfg, include=("team/worker",))
    urls = fake_datadog(monkeypatch)
    fetched = client.fetch_all(online_cfg)
    assert "https://api.datadoghq.com/api/v1/service_dependencies/team/worker" in urls
    raw = online_cfg.raw_dir
    assert sorted(p.name for p in raw.iterdir()) == [
        "definition.json", "dependencies-team_worker.json", "dependencies.json", "resources.json",
        "types.json"]
    assert json.loads((raw / "dependencies.json").read_text()) == fetched.deps
    assert json.loads((raw / "resources.json").read_text()) == fetched.resources
    assert not list(online_cfg.output_dir.glob(".raw-*"))


def test_fetch_all_replaces_stale_raw_files(monkeypatch, online_cfg):
    (online_cfg.raw_dir / "dependencies-removed_service.json").write_text("{}")
    (online_cfg.raw_dir / "definition.json").write_text("{}")
    fake_datadog(monkeypatch, definition_status=404)
    client.fetch_all(online_cfg)
    assert sorted(p.name for p in online_cfg.raw_dir.iterdir()) == [
        "dependencies.json", "resources.json", "types.json"]


def test_fetch_all_with_no_raw_writes_nothing(monkeypatch, online_cfg):
    (online_cfg.raw_dir / "dependencies.json").write_text('{"previous": "run"}')
    fake_datadog(monkeypatch)
    fetched = client.fetch_all(replace(online_cfg, save_raw=False))
    assert fetched.resources == [{"resource": "GET /cart", "hits": 7}]
    assert [p.name for p in online_cfg.raw_dir.iterdir()] == ["dependencies.json"]
    assert sorted(p.name for p in online_cfg.output_dir.iterdir()) == ["raw"]


def test_fetch_all_failure_leaves_raw_untouched(monkeypatch, online_cfg):
    (online_cfg.raw_dir / "dependencies.json").write_text('{"previous": "run"}')
    fake_datadog(monkeypatch, spans_status=500)
    with pytest.raises(client.DatadogAPIError, match="500"):
        client.fetch_all(online_cfg)
    assert [p.name for p in online_cfg.raw_dir.iterdir()] == ["dependencies.json"]
    assert json.loads((online_cfg.raw_dir / "dependencies.json").read_text()) == {"previous": "run"}
    assert not list(online_cfg.output_dir.glob(".raw-*"))


def test_fetch_all_offline_writes_nothing(offline_cfg):
    before = {p.name: p.read_bytes() for p in offline_cfg.raw_dir.iterdir()}
    client.fetch_all(offline_cfg)
    assert {p.name: p.read_bytes() for p in offline_cfg.raw_dir.iterdir()} == before


def _limited(reset="7"):
    return FakeResponse(429, {"errors": ["Too many requests"]},
                        {"x-ratelimit-reset": reset, "x-ratelimit-name": "spans_public_api"})


def test_429_retried_after_the_reset_datadog_gives(monkeypatch, online_cfg, sleeps):
    answers = [_limited("7"), _limited("3"), FakeResponse(200, {"data": [bucket({"resource_name": "GET /a"}, 1)]})]
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: answers.pop(0))
    assert client.fetch_resources(online_cfg) == [{"resource": "GET /a", "hits": 1}]
    assert sleeps == [7, 3]


def test_429_gives_up_after_max_retries(monkeypatch, online_cfg, sleeps):
    calls = []
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: calls.append(1) or _limited("1"))
    with pytest.raises(client.DatadogAPIError, match="429"):
        client.fetch_service_dependencies(online_cfg)
    assert len(calls) == client.MAX_RETRIES + 1
    assert sleeps == [1] * client.MAX_RETRIES


@pytest.mark.parametrize("reset", ["", "soon", "3600"])
def test_429_without_a_usable_reset_fails_at_once(monkeypatch, online_cfg, sleeps, reset):
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: _limited(reset))
    with pytest.raises(client.DatadogAPIError, match="429"):
        client.fetch_service_dependencies(online_cfg)
    assert sleeps == []


def test_span_types_one_query_grouped_by_service_then_type(monkeypatch, online_cfg):
    sent = []

    def fake_post(url, headers, json, timeout):
        sent.append(json["data"]["attributes"])
        return FakeResponse(200, {"data": [
            bucket({"service": "orders-db", "type": "sql"}, 900),
            bucket({"service": "cart", "type": "web"}, 50),
            bucket({"service": "cart", "type": ""}, 20),
        ]})

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.fetch_span_types(online_cfg, ["cart", "orders-db"]) == {
        "orders-db": {"sql": 900}, "cart": {"web": 50, "": 20}}
    (attrs,) = sent
    assert attrs["filter"]["query"] == 'env:prod service:("cart" OR "orders-db")'
    assert [g["facet"] for g in attrs["group_by"]] == ["service", "type"]


def test_span_types_skip_the_call_without_neighbours(monkeypatch, online_cfg):
    monkeypatch.setattr(client.requests, "post", lambda *a, **k: pytest.fail("no call expected"))
    assert client.fetch_span_types(online_cfg, []) == {}


def test_span_types_optional_offline(offline_cfg):
    (offline_cfg.raw_dir / "types.json").unlink(missing_ok=True)
    assert client.fetch_span_types(offline_cfg, ["x"]) == {}
