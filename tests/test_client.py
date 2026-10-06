"""Datadog calls with requests replaced by fakes; nothing goes over the network."""
import json

import pytest

from datadog_structurizr import client


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_dependencies_request_and_raw_copy(monkeypatch, online_cfg):
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
    assert json.loads((online_cfg.raw_dir / "dependencies.json").read_text()) == deps


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
            return FakeResponse(200, {"data": {"buckets": []}})
        return FakeResponse(200, {"data": {"buckets": [
            {"by": {"resource_name": "GET /cart"}, "computes": {"c0": 7}},
            {"by": {}, "computes": {"c0": 1}},
        ]}})

    monkeypatch.setattr(client.requests, "post", fake_post)
    assert client.fetch_resources(online_cfg) == [{"resource": "GET /cart", "hits": 7}]
    assert queries == ["service:checkout-web env:prod @span.kind:(server OR consumer)",
                       "service:checkout-web env:prod"]


def test_definition_is_optional(monkeypatch, online_cfg):
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: FakeResponse(404, {}))
    assert client.fetch_service_definition(online_cfg) == {}


def test_offline_reads_raw_files(offline_cfg):
    assert client.fetch_service_dependencies(offline_cfg)["name"] == "checkout-web"
    assert client.fetch_resources(offline_cfg)


def test_included_service_dependencies_saved_under_own_name(monkeypatch, online_cfg):
    urls = []

    def fake_get(url, headers, params, timeout):
        urls.append(url)
        return FakeResponse(200, {"name": "w", "calls": [], "called_by": []})

    monkeypatch.setattr(client.requests, "get", fake_get)
    client.fetch_service_dependencies(online_cfg, "team/worker")
    assert urls == ["https://api.datadoghq.com/api/v1/service_dependencies/team/worker"]
    assert (online_cfg.raw_dir / "dependencies-team_worker.json").is_file()
    assert not (online_cfg.raw_dir / "dependencies.json").exists()
