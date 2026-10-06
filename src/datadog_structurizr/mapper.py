"""Map Datadog APM data onto a C4 model.

Mapping rules:
  - The target service is a container inside a software system of the same name.
  - Datastore-looking dependencies are containers inside that system (owned data).
  - SaaS / cloud-API-looking dependencies are external software systems.
  - Every other neighbouring service is an internal software system.
  - Components are the target's entry points (span resource_name): HTTP
    routes grouped by their first meaningful path segment, and other
    resources such as consumers and jobs one each. They are labelled as
    endpoint groups and entry points, because APM sees the API surface, not
    the code structure behind it.

Classification is name-based heuristics; use [classify] in the config file or
the hint tuples below when they guess wrong.
"""
from __future__ import annotations

import fnmatch
import re
from collections import defaultdict
from typing import Any

from .config import Config
from .model import C4Model, Element

EXTERNAL_HINTS = (
    "stripe", "auth0", "okta", "twilio", "sendgrid", "paypal", "adyen",
    "aws.", "s3", "sqs", "sns", "kinesis", "bigquery", "snowflake",
    "salesforce", "hubspot", "segment", "googleapis", "amazonaws",
)
DATASTORE_HINTS = (
    "postgres", "mysql", "mariadb", "mongo", "redis", "memcache", "cassandra",
    "dynamodb", "elasticsearch", "opensearch", "clickhouse", "sqlserver",
    "oracle", "db", "kafka", "rabbitmq",
)
HTTP_GROUP = "HTTP endpoint group"
ENTRY_POINT = "Entry point"
# Probe endpoints are not architecture; drop them from L2.
_PROBE_RE = re.compile(r"/(health|healthz|healthcheck|ready|readyz|live|livez|ping|metrics)/?$",
                       re.IGNORECASE)

_HTTP_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", re.IGNORECASE)
_NOISE_SEGMENT = re.compile(r"^(api|v\d+|\{.*\}|:.*|<.*>|\d+|\?.*)$", re.IGNORECASE)


def _key(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    return f"e_{cleaned}" if not cleaned or cleaned[0].isdigit() else cleaned


def _matches(name: str, hints: tuple[str, ...]) -> bool:
    lower = name.lower()
    tokens = set(re.split(r"[^a-z0-9]+", lower))
    # "db" only as a whole token, everything else as substring
    return any((h in tokens) if h == "db" else (h in lower) for h in hints)


def _definition_attrs(definition: dict[str, Any]) -> dict[str, Any]:
    schema = definition.get("data", {}).get("attributes", {}).get("schema", {}) or {}
    return {
        "description": schema.get("description") or "",
        "languages": schema.get("languages") or [],
        "team": schema.get("team") or "",
    }


def _group_resources(resources: list[dict[str, Any]],
                     max_components: int = 12) -> list[tuple[str, str, list[str], int]]:
    """Return [(component name, technology, sample resources, hits)] sorted by hits."""
    groups: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for r in resources:
        res, hits = r["resource"], r["hits"]
        m = _HTTP_RE.match(res)
        if m and _PROBE_RE.search(m.group(2)):
            continue
        if m:
            segments = [s for s in m.group(2).split("/") if s and not _NOISE_SEGMENT.match(s)]
            name = f"{segments[0].title() if segments else 'Root'} API"
            groups[(name, HTTP_GROUP)].append((res, hits))
        else:
            groups[(res[:40], ENTRY_POINT)].append((res, hits))

    ranked = sorted(
        ((name, tech, [r for r, _ in items], sum(h for _, h in items))
         for (name, tech), items in groups.items()),
        key=lambda g: g[3], reverse=True,
    )
    if len(ranked) > max_components:
        head, tail = ranked[:max_components - 1], ranked[max_components - 1:]
        head.append(("Other", "mixed",
                     [r for g in tail for r in g[2]], sum(g[3] for g in tail)))
        ranked = head
    return ranked


def _glob(name: str, patterns: tuple[str, ...]) -> bool:
    lower = name.lower()
    return any(fnmatch.fnmatchcase(lower, pat.lower()) for pat in patterns)


def _container_meta(meta: dict[str, Any]) -> tuple[str, str]:
    return (meta["description"] or "Application container.",
            ", ".join(meta["languages"]) or "APM service")


def build_model(deps: dict[str, Any], resources: list[dict[str, Any]],
                definition: dict[str, Any], cfg: Config,
                member_deps: dict[str, dict[str, Any]] | None = None) -> C4Model:
    """Build the model.

    member_deps: dependencies of the services named in cfg.include, which
    become containers of the target system next to the target service.
    """
    target = cfg.service
    member_deps = member_deps or {}
    meta = _definition_attrs(definition)
    description, tech = _container_meta(meta)

    person = (Element("user", cfg.person_name, "person", cfg.person_description)
              if cfg.person_enabled else None)
    system_name = cfg.system_name or target
    system = Element(f"{_key(system_name)}_system", system_name, "system",
                     cfg.system_description or meta["description"] or f"System containing {target}.")
    container = Element(_key(target), target, "container", description,
                        technology=tech, parent_key=system.key)
    system.children.append(container)
    for name in cfg.include:
        system.children.append(Element(_key(name), name, "container",
                                       "Container of the system observed in APM.",
                                       technology="APM service", parent_key=system.key))

    model = C4Model(
        name=f"{system_name} - C4",
        description=f"Generated from Datadog APM ({cfg.env}, last {cfg.lookback_hours}h)"
                    + (f"; owner team: {meta['team']}" if meta["team"] else ""),
        person=person, target_system=system, target_container=container,
    )

    def neighbour(name: str) -> Element | None:
        """The element for a dependency name, creating it on first sight; None if ignored."""
        if _glob(name, cfg.ignore):
            return None
        key = _key(name)
        existing = next((e for e in model.all_elements() if e.key == key), None)
        if existing:
            return existing
        # Explicit classification first, then the name hints.
        if _glob(name, cfg.datastores):
            kind = "datastore"
        elif _glob(name, cfg.external):
            kind = "external"
        elif _glob(name, cfg.internal):
            kind = "internal"
        elif _matches(name, DATASTORE_HINTS) and not _matches(name, EXTERNAL_HINTS):
            kind = "datastore"
        elif _matches(name, EXTERNAL_HINTS):
            kind = "external"
        else:
            kind = "internal"
        if kind == "datastore":
            el = Element(key, name, "container", "Datastore used by the system.",
                         technology="Datastore", database=True, parent_key=system.key)
            system.children.append(el)
        elif kind == "external":
            el = Element(key, name, "system", "External service.", external=True)
            model.systems.append(el)
        else:
            el = Element(key, name, "system", "Internal service observed in APM.")
            model.systems.append(el)
        return el

    # L0/L1 relationships at container level; Structurizr derives the
    # system-level ones (implied relationships) for the context view.
    if person:
        model.relate(person.key, container.key, "Uses", "HTTPS")
    for source_name, source_deps in [(target, deps), *member_deps.items()]:
        source = neighbour(source_name)
        if source is None:
            continue
        for name in source_deps.get("calls", []) or []:
            el = neighbour(name)
            if el is not None:
                model.relate(source.key, el.key, "Calls")
        for name in source_deps.get("called_by", []) or []:
            el = neighbour(name)
            if el is not None:
                model.relate(el.key, source.key, "Calls")

    # L2 components from entry-point resources. HTTP routes are called by the
    # person or, without one, by the services observed calling the target.
    callers = ([person.key] if person else
               [r.source_key for r in model.relationships if r.target_key == container.key])
    groups = _group_resources(resources, cfg.max_components)
    if not groups:
        groups = [("Request Handlers", "unknown",
                   ["No indexed spans found - refine by hand."], 0)]
    for name, comp_tech, samples, hits in groups:
        shown = "; ".join(samples[:3]) + (f" (+{len(samples) - 3} more)" if len(samples) > 3 else "")
        comp = Element(f"{container.key}__{_key(name)}", name, "component",
                       f"{shown}" + (f" - {hits} spans" if hits else ""),
                       technology=comp_tech, parent_key=container.key)
        container.children.append(comp)
        if comp_tech == HTTP_GROUP:
            for caller in callers:
                model.relate(caller, comp.key, "Calls", "HTTPS")

    return model
