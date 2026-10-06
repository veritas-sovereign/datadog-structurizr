"""Datadog API calls.

Plain `requests` so the endpoint being hit is explicit and easy to debug.
Once every call has succeeded, the responses replace output/raw/ as a whole,
so a run can be replayed with --offline (no credentials, no API calls) while
tuning the diagrams, and raw/ never mixes responses from different runs.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from .config import Config


class DatadogAPIError(RuntimeError):
    """A Datadog call failed; the run stops rather than draw from partial data."""


# A 429 is retried after the wait Datadog asks for in x-ratelimit-reset
# (seconds, checked on a live account), at most this often and this long.
MAX_RETRIES = 2
MAX_WAIT_SECONDS = 60


def _retry_wait(resp: requests.Response) -> int | None:
    """Seconds to wait before retrying a 429, or None to give up."""
    try:
        wait = int(resp.headers.get("x-ratelimit-reset", ""))
    except (TypeError, ValueError):
        return None
    return max(wait, 1) if wait <= MAX_WAIT_SECONDS else None


def _send(call: Callable[..., requests.Response], url: str, **kwargs: Any) -> requests.Response:
    """requests.get or requests.post, retrying when Datadog answers 429."""
    resp = call(url, **kwargs)
    for _ in range(MAX_RETRIES):
        wait = _retry_wait(resp) if resp.status_code == 429 else None
        if wait is None:
            return resp
        limit = resp.headers.get("x-ratelimit-name", "Datadog")
        print(f"      rate limited ({limit}); retrying in {wait}s", file=sys.stderr)
        time.sleep(wait)
        resp = call(url, **kwargs)
    return resp


def _check(resp: requests.Response, what: str) -> None:
    if resp.status_code != 200:
        raise DatadogAPIError(f"Datadog API error {resp.status_code} for {what}: {resp.text[:500]}")


def _headers(cfg: Config) -> dict[str, str]:
    return {
        "DD-API-KEY": cfg.api_key,
        "DD-APPLICATION-KEY": cfg.app_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _base(cfg: Config) -> str:
    return f"https://api.{cfg.site}"


def _replace_raw(cfg: Config, files: dict[str, Any]) -> None:
    """Write the responses to a new directory, then swap it in for raw/."""
    staging = Path(tempfile.mkdtemp(prefix=".raw-new-", dir=cfg.output_dir))
    try:
        for name, data in files.items():
            (staging / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    old = staging.with_name(staging.name.replace(".raw-new-", ".raw-old-"))
    if cfg.raw_dir.exists():
        cfg.raw_dir.rename(old)
    staging.rename(cfg.raw_dir)
    shutil.rmtree(old, ignore_errors=True)


def _load(cfg: Config, name: str) -> Any:
    path: Path = cfg.raw_dir / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"--offline: {path} not found. Run once online first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _dependencies_name(cfg: Config, service: str) -> str:
    return ("dependencies" if service == cfg.service
            else "dependencies-" + re.sub(r"[^A-Za-z0-9._-]", "_", service))


def fetch_service_dependencies(cfg: Config, service: str | None = None) -> dict[str, Any]:
    """Upstream (`called_by`) and downstream (`calls`) services of one service.

    `service` defaults to the target; other services (system.include) are
    saved as raw/dependencies-<service>.json.

    GET /api/v1/service_dependencies/{service}?env=&start=&end=
    Response: {"name": "...", "calls": [...], "called_by": [...]}
    Docs: https://docs.datadoghq.com/api/latest/service-dependencies/
    """
    service = service or cfg.service
    if cfg.offline:
        return _load(cfg, _dependencies_name(cfg, service))

    end = int(time.time())
    params = {"env": cfg.env, "start": end - cfg.lookback_hours * 3600, "end": end}
    resp = _send(
        requests.get, f"{_base(cfg)}/api/v1/service_dependencies/{service}",
        headers=_headers(cfg), params=params, timeout=30,
    )
    _check(resp, f"service dependencies of {service}")
    return resp.json()


def _aggregate(cfg: Config, query: str, facets: list[tuple[str, int]]) -> list[dict[str, Any]]:
    """Span counts grouped by facets, as [{"by": {facet: value}, "compute": {"c0": n}}]."""
    order = {"aggregation": "count", "order": "desc", "type": "measure"}
    body = {
        "data": {
            "type": "aggregate_request",
            "attributes": {
                "filter": {"from": f"now-{cfg.lookback_hours}h", "to": "now", "query": query},
                "compute": [{"aggregation": "count", "type": "total"}],
                "group_by": [{"facet": f, "limit": limit, "sort": order} for f, limit in facets],
            },
        }
    }
    resp = _send(
        requests.post, f"{_base(cfg)}/api/v2/spans/analytics/aggregate",
        headers=_headers(cfg), json=body, timeout=60,
    )
    _check(resp, f"spans aggregate ({query})")
    # Response: {"data": [{"type": "bucket", "attributes": {"by": {...},
    # "compute": {"c0": n}}}], "meta": {...}}, checked against the live API.
    data = resp.json().get("data")
    if not isinstance(data, list):
        raise DatadogAPIError(f"spans aggregate ({query}): expected a list in 'data', "
                              f"got {type(data).__name__}")
    return [b.get("attributes") or {} for b in data]


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
    # show up as components; fall back only when that query succeeds with no
    # buckets (the tracer doesn't set span.kind), never after a failed call.
    buckets = _aggregate(cfg, f"{base} @span.kind:(server OR consumer)", [("resource_name", 100)])
    if not buckets:
        buckets = _aggregate(cfg, base, [("resource_name", 100)])

    return [
        {
            "resource": str(b.get("by", {}).get("resource_name", "")),
            "hits": int((b.get("compute") or {}).get("c0") or 0),
        }
        for b in buckets
        if b.get("by", {}).get("resource_name")
    ]


def fetch_service_definition(cfg: Config) -> dict[str, Any]:
    """Service Catalog metadata (description, team, languages).

    Optional: 404 (no definition) gives {}; any other error stops the run.

    GET /api/v2/services/definitions/{service_name}
    """
    if cfg.offline:
        try:
            return _load(cfg, "definition")
        except SystemExit:
            return {}

    resp = _send(
        requests.get, f"{_base(cfg)}/api/v2/services/definitions/{cfg.service}",
        headers=_headers(cfg), timeout=30,
    )
    if resp.status_code == 404:
        # No definition in the Service Catalog: metadata is optional.
        return {}
    _check(resp, f"service definition of {cfg.service}")
    return resp.json()


def fetch_span_types(cfg: Config, services: list[str]) -> dict[str, dict[str, int]]:
    """Span counts per span type for each service, from the services' own spans.

    One spans aggregate grouped by service, then type. A datastore reports one
    type (sql, redis, ...); an application service mostly web or http.
    Returns {service: {type: span count}}; "" is spans with no type.
    """
    if cfg.offline:
        try:
            return _load(cfg, "types")
        except SystemExit:
            return {}  # raw/ from before types were fetched: classify by name
    if not services:
        return {}
    names = " OR ".join('"' + s.replace('"', '\\"') + '"' for s in services)
    buckets = _aggregate(cfg, f"env:{cfg.env} service:({names})",
                         [("service", len(services)), ("type", 10)])
    types: dict[str, dict[str, int]] = {}
    for b in buckets:
        by = b.get("by", {})
        if by.get("service"):
            types.setdefault(str(by["service"]), {})[str(by.get("type") or "")] = \
                int((b.get("compute") or {}).get("c0") or 0)
    return types


@dataclass
class Fetched:
    deps: dict[str, Any]
    member_deps: dict[str, dict[str, Any]]
    resources: list[dict[str, Any]]
    definition: dict[str, Any]
    types: dict[str, dict[str, int]]


def fetch_all(cfg: Config) -> Fetched:
    """Every input of one run. Online, raw/ is replaced only after all calls succeed,
    and not at all with --no-raw."""
    deps = fetch_service_dependencies(cfg)
    member_deps = {name: fetch_service_dependencies(cfg, name) for name in cfg.include}
    neighbours = sorted({n for d in (deps, *member_deps.values())
                         for n in (d.get("calls") or []) + (d.get("called_by") or [])}
                        - {cfg.service, *cfg.include})
    fetched = Fetched(
        deps=deps, member_deps=member_deps,
        resources=fetch_resources(cfg),
        definition=fetch_service_definition(cfg),
        types=fetch_span_types(cfg, neighbours),
    )
    if not cfg.offline and cfg.save_raw:
        files = {"dependencies": fetched.deps, "resources": fetched.resources,
                 "types": fetched.types}
        files.update((_dependencies_name(cfg, name), deps) for name, deps in fetched.member_deps.items())
        if fetched.definition:
            files["definition"] = fetched.definition
        _replace_raw(cfg, files)
    return fetched
