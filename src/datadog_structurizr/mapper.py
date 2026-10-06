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

Classification: [classify] in the config file, then the span type of the
dependency's own spans, then the name hints below.
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
# Span types (the `type` of a service's own spans) seen on a live account.
# A dependency whose most common type is one of these is a datastore; one whose
# most common type is a service type is not, whatever its name suggests. Any
# other type, or none, leaves the decision to the name hints.
DATASTORE_TYPES = frozenset({"sql", "redis", "valkey", "elasticsearch", "opensearch",
                             "dynamodb", "mongodb", "cosmosdb"})
SERVICE_TYPES = frozenset({"web", "http", "rpc", "soap", "serverless"})
HTTP_GROUP = "HTTP endpoint group"
ENTRY_POINT = "Entry point"
UNROUTED = "Unrouted HTTP"
STATIC = "Static content"
# Probe endpoints are not architecture; drop them from L2. A path is a probe
# when its last segment is one of these or ends in "health" (app-health,
# service-health), or when any segment is "actuator" (Spring Boot).
_PROBE_LAST = re.compile(r"^([\w.-]*health|healthz|healthcheck|ready|readyz|live|livez|ping|metrics)$",
                         re.IGNORECASE)
# Files a web server hands out, optionally pre-compressed (.br, .gz).
_STATIC_RE = re.compile(r"\.(m?js|css|map|png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|eot|html?|txt)"
                        r"(\.(br|gz))?$", re.IGNORECASE)

_HTTP_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?:\s+(\S+))?$", re.IGNORECASE)
_NOISE_SEGMENT = re.compile(r"^(api|v\d+|\{.*\}|:.*|<.*>|\d+|\?.*)$", re.IGNORECASE)


def _key(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    return f"e_{cleaned}" if not cleaned or cleaned[0].isdigit() else cleaned


class _Keys:
    """Hands out identifiers that are unique within one model.

    _key() maps different names onto the same identifier (cart-service,
    cart.service and cart_service are all cart_service). The first element
    keeps it; each later one gets _2, _3, ... and a warning, so two services
    are never drawn as one.
    """

    def __init__(self) -> None:
        self._owner: dict[str, str] = {}   # identifier -> what it was made from
        self.warnings: list[str] = []

    def __call__(self, name: str, base: str | None = None) -> str:
        base = base or _key(name)
        key, n = base, 2
        while key in self._owner:
            key, n = f"{base}_{n}", n + 1
        if key != base:
            self.warnings.append(f"'{name}' and '{self._owner[base]}' both make the identifier "
                                 f"{base}; '{name}' is {key}")
        self._owner[key] = name
        return key


def _hint(name: str, hints: tuple[str, ...]) -> str:
    """The first hint the name matches, or ""."""
    lower = name.lower()
    tokens = set(re.split(r"[^a-z0-9]+", lower))
    # "db" only as a whole token, everything else as substring
    return next((h for h in hints if ((h in tokens) if h == "db" else (h in lower))), "")


def _definition_attrs(definition: dict[str, Any]) -> dict[str, Any]:
    schema = definition.get("data", {}).get("attributes", {}).get("schema", {}) or {}
    return {
        "description": schema.get("description") or "",
        "languages": schema.get("languages") or [],
        "team": schema.get("team") or "",
    }


def _strip_prefix(path: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        prefix = prefix.rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return path[len(prefix):] or "/"
    return path


def _is_probe(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    return bool(segments) and (_PROBE_LAST.match(segments[-1]) is not None
                               or any(s.lower() == "actuator" for s in segments))


def _group_resources(resources: list[dict[str, Any]], max_components: int = 12,
                     strip_prefixes: tuple[str, ...] = ()) -> list[tuple[str, str, list[str], int]]:
    """Return [(component name, technology, sample resources, hits)] sorted by hits."""
    groups: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for r in resources:
        res, hits = r["resource"], r["hits"]
        m = _HTTP_RE.match(res)
        if not m:
            groups[(res[:40], ENTRY_POINT)].append((res, hits))
            continue
        if m.group(2) is None:
            # A method with no route: the tracer did not record which endpoint.
            groups[(UNROUTED, HTTP_GROUP)].append((res, hits))
            continue
        path = _strip_prefix(m.group(2), strip_prefixes)
        if _is_probe(path):
            continue
        if _STATIC_RE.search(path):
            groups[(STATIC, HTTP_GROUP)].append((res, hits))
            continue
        segments = [s for s in path.split("/") if s and not _NOISE_SEGMENT.match(s)]
        name = f"{segments[0].title() if segments else 'Root'} API"
        groups[(name, HTTP_GROUP)].append((res, hits))

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


def _pattern(name: str, patterns: tuple[str, ...]) -> str:
    """The first pattern the name matches, or ""."""
    lower = name.lower()
    return next((pat for pat in patterns if fnmatch.fnmatchcase(lower, pat.lower())), "")


def _classify(name: str, span_type: str, cfg: Config) -> tuple[str, str]:
    """(datastore | external | internal, the reason), for one dependency.

    Explicit classification first, then the span type Datadog recorded, then
    the name hints. The reason is written to the DSL, so a wrong guess can be
    traced to the rule that made it.
    """
    for kind, option, patterns in (("datastore", "datastores", cfg.datastores),
                                   ("external", "external", cfg.external),
                                   ("internal", "internal", cfg.internal)):
        pattern = _pattern(name, patterns)
        if pattern:
            return kind, f"[classify] {option} pattern {pattern}"
    external = _hint(name, EXTERNAL_HINTS)
    if span_type in DATASTORE_TYPES:
        return "datastore", f"span type {span_type}"
    if span_type in SERVICE_TYPES:
        if external:
            return "external", f"span type {span_type} and name hint {external}"
        return "internal", f"span type {span_type}"
    datastore = _hint(name, DATASTORE_HINTS)
    if datastore and not external:
        return "datastore", f"name hint {datastore}"
    if external:
        return "external", f"name hint {external}"
    return "internal", "no span type or name hint matched"


def _container_meta(meta: dict[str, Any]) -> tuple[str, str]:
    return (meta["description"] or "Application container.",
            ", ".join(meta["languages"]) or "APM service")


def _span_type(counts: dict[str, int] | None) -> str:
    """The most common non-empty span type, or "" when there is none."""
    typed = {t: n for t, n in (counts or {}).items() if t}
    return max(sorted(typed), key=typed.__getitem__) if typed else ""


def build_model(deps: dict[str, Any], resources: list[dict[str, Any]],
                definition: dict[str, Any], cfg: Config,
                member_deps: dict[str, dict[str, Any]] | None = None,
                types: dict[str, dict[str, int]] | None = None) -> C4Model:
    """Build the model.

    member_deps: dependencies of the services named in cfg.include, which
    become containers of the target system next to the target service.
    types: span counts per span type of each neighbouring service.
    """
    target = cfg.service
    member_deps = member_deps or {}
    types = types or {}
    meta = _definition_attrs(definition)
    description, tech = _container_meta(meta)
    keys = _Keys()

    person = (Element(keys(cfg.person_name, "user"), cfg.person_name, "person", cfg.person_description)
              if cfg.person_enabled else None)
    system_name = cfg.system_name or target
    system = Element(keys(system_name, f"{_key(system_name)}_system"), system_name, "system",
                     cfg.system_description or meta["description"] or f"System containing {target}.")
    container = Element(keys(target), target, "container", description,
                        technology=tech, parent_key=system.key)
    system.children.append(container)
    # APM services by name: a name met again is the same element.
    services = {target: container}
    for name in cfg.include:
        if name not in services:
            services[name] = Element(keys(name), name, "container",
                                     "Container of the system observed in APM.",
                                     technology="APM service", parent_key=system.key,
                                     basis="[system] include")
            system.children.append(services[name])

    model = C4Model(
        name=f"{system_name} - C4",
        description=f"Generated from Datadog APM ({cfg.env}, last {cfg.lookback_hours}h)"
                    + (f"; owner team: {meta['team']}" if meta["team"] else ""),
        person=person, target_system=system, target_container=container,
    )

    def neighbour(name: str) -> Element | None:
        """The element for a dependency name, creating it on first sight; None if ignored."""
        if _pattern(name, cfg.ignore):
            return None
        if name in services:
            return services[name]
        key = keys(name)
        span_type = _span_type(types.get(name))
        kind, basis = _classify(name, span_type, cfg)
        if kind == "datastore":
            el = Element(key, name, "container", "Datastore used by the system.",
                         technology=span_type if span_type in DATASTORE_TYPES else "Datastore",
                         database=True, parent_key=system.key, basis=basis)
            system.children.append(el)
        elif kind == "external":
            el = Element(key, name, "system", "External service.", external=True, basis=basis)
            model.systems.append(el)
        else:
            el = Element(key, name, "system", "Internal service observed in APM.", basis=basis)
            model.systems.append(el)
        services[name] = el
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
    groups = _group_resources(resources, cfg.max_components, cfg.strip_prefixes)
    if not groups:
        groups = [("Request Handlers", "unknown",
                   ["No indexed spans found - refine by hand."], 0)]
    for name, comp_tech, samples, hits in groups:
        shown = "; ".join(samples[:3]) + (f" (+{len(samples) - 3} more)" if len(samples) > 3 else "")
        comp = Element(keys(name, f"{container.key}__{_key(name)}"), name, "component",
                       f"{shown}" + (f" - {hits} spans" if hits else ""),
                       technology=comp_tech, parent_key=container.key)
        container.children.append(comp)
        if comp_tech == HTTP_GROUP:
            for caller in callers:
                model.relate(caller, comp.key, "Calls", "HTTPS")

    model.warnings = keys.warnings
    return model
