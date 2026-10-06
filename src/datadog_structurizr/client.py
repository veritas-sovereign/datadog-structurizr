"""Datadog API calls.

Plain `requests` so the endpoint being hit is explicit and easy to debug.
Every response is saved under output/raw/ so a run can be replayed with
--offline (no credentials, no API calls) while tuning the diagrams.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from .config import Config


def _headers(cfg: Config) -> dict[str, str]:
    return {
        "DD-API-KEY": cfg.api_key,
        "DD-APPLICATION-KEY": cfg.app_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _base(cfg: Config) -> str:
    return f"https://api.{cfg.site}"


def _save(cfg: Config, name: str, data: Any) -> None:
    (cfg.raw_dir / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _load(cfg: Config, name: str) -> Any:
    path: Path = cfg.raw_dir / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"--offline: {path} not found. Run once online first.")
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_service_dependencies(cfg: Config, service: str | None = None) -> dict[str, Any]:
    """Upstream (`called_by`) and downstream (`calls`) services of one service.

    `service` defaults to the target; other services (system.include) are
    saved as raw/dependencies-<service>.json.

    GET /api/v1/service_dependencies/{service}?env=&start=&end=
    Response: {"name": "...", "calls": [...], "called_by": [...]}
    Docs: https://docs.datadoghq.com/api/latest/service-dependencies/
    """
    service = service or cfg.service
    name = ("dependencies" if service == cfg.service
            else "dependencies-" + re.sub(r"[^A-Za-z0-9._-]", "_", service))
    if cfg.offline:
        return _load(cfg, name)

    end = int(time.time())
    params = {"env": cfg.env, "start": end - cfg.lookback_hours * 3600, "end": end}
    resp = requests.get(
        f"{_base(cfg)}/api/v1/service_dependencies/{service}",
        headers=_headers(cfg), params=params, timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Datadog API error {resp.status_code} for {service}: {resp.text[:500]}")
    data = resp.json()
    _save(cfg, name, data)
    return data


def _aggregate_resources(cfg: Config, query: str) -> list[dict[str, Any]]:
    body = {
        "data": {
            "type": "aggregate_request",
            "attributes": {
                "filter": {"from": f"now-{cfg.lookback_hours}h", "to": "now", "query": query},
                "compute": [{"aggregation": "count", "type": "total"}],
                "group_by": [{
                    "facet": "resource_name",
                    "limit": 100,
                    "sort": {"aggregation": "count", "order": "desc", "type": "measure"},
                }],
            },
        }
    }
    resp = requests.post(
        f"{_base(cfg)}/api/v2/spans/analytics/aggregate",
        headers=_headers(cfg), json=body, timeout=60,
    )
    if resp.status_code != 200:
        print(f"      warning: spans aggregate {resp.status_code}: {resp.text[:300]}")
        return []
    return resp.json().get("data", {}).get("buckets", []) or []


def fetch_resources(cfg: Config) -> list[dict[str, Any]]:
    """Entry-point resources (endpoints, handlers) of the target, with hit counts.

    POST /api/v2/spans/analytics/aggregate grouped by resource_name.
    Only covers indexed spans (retention filters), so counts are relative,
    not absolute traffic. Returns [{"resource": str, "hits": int}, ...].
    """
    if cfg.offline:
        return _load(cfg, "resources")

    base = f"service:{cfg.service} env:{cfg.env}"
    # Prefer server/consumer spans so client calls (SQL, outbound HTTP) don't
    # show up as components; fall back if the tracer doesn't set span.kind.
    buckets = _aggregate_resources(cfg, f"{base} @span.kind:(server OR consumer)")
    if not buckets:
        buckets = _aggregate_resources(cfg, base)

    resources = [
        {
            "resource": str(b.get("by", {}).get("resource_name", "")),
            "hits": int((b.get("computes") or {}).get("c0") or 0),
        }
        for b in buckets
        if b.get("by", {}).get("resource_name")
    ]
    _save(cfg, "resources", resources)
    return resources


def fetch_service_definition(cfg: Config) -> dict[str, Any]:
    """Service Catalog metadata (description, team, languages). Optional.

    GET /api/v2/services/definitions/{service_name}
    """
    if cfg.offline:
        try:
            return _load(cfg, "definition")
        except SystemExit:
            return {}

    resp = requests.get(
        f"{_base(cfg)}/api/v2/services/definitions/{cfg.service}",
        headers=_headers(cfg), timeout=30,
    )
    if resp.status_code != 200:
        # Metadata is nice-to-have; don't fail the whole run.
        return {}
    data = resp.json()
    _save(cfg, "definition", data)
    return data
