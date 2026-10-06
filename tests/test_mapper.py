from datadog_structurizr.mapper import (ENTRY_POINT, HTTP_GROUP, STATIC, UNROUTED, _group_resources,
                                        build_model)

MAX_COMPONENTS = 12


def _model(cfg, calls=(), called_by=(), resources=()):
    return build_model({"calls": list(calls), "called_by": list(called_by)},
                       [{"resource": r, "hits": h} for r, h in resources], {}, cfg)


def test_dependencies_are_classified(offline_cfg):
    m = _model(offline_cfg, calls=["orders-db", "redis", "stripe-api", "aws.sqs", "cart-service"])
    db = {c.name for c in m.target_system.children if c.database}
    ext = {s.name for s in m.systems if s.external}
    internal = {s.name for s in m.systems if not s.external}
    assert db == {"orders-db", "redis"}
    assert ext == {"stripe-api", "aws.sqs"}
    assert internal == {"cart-service"}


def test_db_hint_matches_whole_token_only(offline_cfg):
    m = _model(offline_cfg, calls=["feedback-service"])
    assert [s.name for s in m.systems] == ["feedback-service"]


def test_upstream_and_downstream_relationships(offline_cfg):
    m = _model(offline_cfg, calls=["cart-service"], called_by=["api-gateway"])
    pairs = {(r.source_key, r.target_key) for r in m.relationships}
    assert ("checkout_web", "cart_service") in pairs
    assert ("api_gateway", "checkout_web") in pairs
    assert ("user", "checkout_web") in pairs


def test_self_dependency_is_ignored(offline_cfg):
    m = _model(offline_cfg, calls=["checkout-web"])
    assert not m.systems
    assert all(r.source_key != r.target_key for r in m.relationships)


def test_http_routes_grouped_by_first_meaningful_segment():
    groups = _group_resources([
        {"resource": "GET /api/v1/cart/{id}", "hits": 5},
        {"resource": "POST /api/v2/cart/items", "hits": 3},
        {"resource": "GET /orders/:id", "hits": 1},
    ])
    assert [(g[0], g[3]) for g in groups] == [("Cart API", 8), ("Orders API", 1)]


def test_probe_endpoints_dropped_but_status_routes_kept():
    groups = _group_resources([
        {"resource": "GET /health", "hits": 100},
        {"resource": "GET /readyz", "hits": 100},
        {"resource": "GET /metrics", "hits": 100},
        {"resource": "GET /checkout/{id}/status", "hits": 1},
    ])
    assert [g[0] for g in groups] == ["Checkout API"]


def test_components_capped_with_other_bucket():
    resources = [{"resource": f"GET /r{i}", "hits": 100 - i} for i in range(MAX_COMPONENTS + 5)]
    groups = _group_resources(resources)
    assert len(groups) == MAX_COMPONENTS
    assert groups[-1][0] == "Other"
    assert groups[-1][3] == sum(100 - i for i in range(MAX_COMPONENTS - 1, MAX_COMPONENTS + 5))


def test_component_cap_is_configurable(offline_cfg):
    import dataclasses
    cfg = dataclasses.replace(offline_cfg, max_components=3)
    m = _model(cfg, resources=[(f"GET /r{i}", 10 - i) for i in range(6)])
    names = [c.name for c in m.target_container.children]
    assert names == ["R0 API", "R1 API", "Other"]


def test_components_labelled_as_endpoint_groups_and_entry_points(offline_cfg):
    m = _model(offline_cfg, resources=[("order.created consume", 10), ("GET /cart", 5)])
    assert sorted(c.technology for c in m.target_container.children) == [ENTRY_POINT, HTTP_GROUP]


def test_non_http_handlers_have_no_user_edge(offline_cfg):
    m = _model(offline_cfg, resources=[("order.created consume", 10), ("GET /cart", 5)])
    handler = next(c for c in m.target_container.children if c.technology == ENTRY_POINT)
    assert not any(r.target_key == handler.key for r in m.relationships)


def test_placeholder_component_when_no_resources(offline_cfg):
    m = _model(offline_cfg)
    assert [c.name for c in m.target_container.children] == ["Request Handlers"]


def test_definition_metadata_used(offline_cfg):
    definition = {"data": {"attributes": {"schema": {
        "description": "Checkout UI", "languages": ["node", "go"], "team": "payments"}}}}
    m = build_model({}, [], definition, offline_cfg)
    assert m.target_container.technology == "node, go"
    assert m.target_system.description == "Checkout UI"
    assert "payments" in m.description


def _cfg(offline_cfg, **changes):
    import dataclasses
    return dataclasses.replace(offline_cfg, **changes)


def test_included_services_are_containers_with_their_own_dependencies(offline_cfg):
    cfg = _cfg(offline_cfg, include=("checkout-worker",))
    m = build_model({"calls": ["checkout-worker"]}, [], {}, cfg,
                    {"checkout-worker": {"calls": ["orders-db", "billing-service"], "called_by": []}})
    containers = {c.name for c in m.target_system.children}
    assert {"checkout-web", "checkout-worker", "orders-db"} <= containers
    assert "checkout-worker" not in {s.name for s in m.systems}
    pairs = {(r.source_key, r.target_key) for r in m.relationships}
    assert ("checkout_web", "checkout_worker") in pairs
    assert ("checkout_worker", "billing_service") in pairs


def test_ignored_services_are_dropped_everywhere(offline_cfg):
    cfg = _cfg(offline_cfg, ignore=("OTEL-*", "datadog-agent"))
    m = _model(cfg, calls=["otel-collector", "datadog-agent", "cart-service"], called_by=["otel-gw"])
    assert [s.name for s in m.systems] == ["cart-service"]
    assert all("otel" not in r.source_key + r.target_key for r in m.relationships)


def test_classification_overrides_beat_name_hints(offline_cfg):
    cfg = _cfg(offline_cfg, datastores=("ledger",), external=("acme-*",), internal=("redis-proxy",))
    m = _model(cfg, calls=["ledger", "acme-pay", "redis-proxy"])
    assert [c.name for c in m.target_system.children if c.database] == ["ledger"]
    assert [s.name for s in m.systems if s.external] == ["acme-pay"]
    assert [s.name for s in m.systems if not s.external] == ["redis-proxy"]


def test_system_name_and_description(offline_cfg):
    cfg = _cfg(offline_cfg, system_name="Checkout", system_description="Pays for carts.")
    m = _model(cfg)
    assert (m.target_system.name, m.target_system.key) == ("Checkout", "Checkout_system")
    assert m.target_system.description == "Pays for carts."
    assert m.target_container.name == "checkout-web"
    assert m.name == "Checkout - C4"


def test_custom_person(offline_cfg):
    cfg = _cfg(offline_cfg, person_name="Shopper", person_description="Buys things.")
    m = _model(cfg)
    assert (m.person.name, m.person.description) == ("Shopper", "Buys things.")


def test_without_person_callers_reach_http_components(offline_cfg):
    cfg = _cfg(offline_cfg, person_enabled=False)
    m = _model(cfg, called_by=["api-gateway"], resources=[("GET /cart", 5), ("nightly.job", 1)])
    assert m.person is None
    comp_targets = {r.target_key for r in m.relationships if r.source_key == "api_gateway"}
    assert "checkout_web__Cart_API" in comp_targets
    assert not any(r.target_key.endswith("nightly_job") for r in m.relationships)


def _names(resources, **kw):
    return [(g[0], g[3]) for g in _group_resources([{"resource": r, "hits": h} for r, h in resources], **kw)]


def test_health_and_actuator_paths_dropped_anywhere():
    assert _names([
        ("GET /shop/health", 9), ("GET /shop/service-health", 9), ("GET /shop/app-health", 9),
        ("GET /shop/api/cart/actuator/info", 9), ("GET /shop/healthcheck", 9),
        ("GET /shop/healthcare-plans", 1),
    ]) == [("Shop API", 1)]


def test_static_files_grouped_once():
    groups = _group_resources([{"resource": r, "hits": 2} for r in (
        "GET /index.html", "GET /static/bundle.js.br", "GET /assets/app.css",
        "GET /img/logo@2x.jpg", "GET /fonts/x.woff2")])
    assert [(g[0], g[1], g[3]) for g in groups] == [(STATIC, HTTP_GROUP, 10)]


def test_method_without_route_is_one_unrouted_group():
    groups = _group_resources([{"resource": "GET", "hits": 5}, {"resource": "POST", "hits": 3},
                               {"resource": "order.created consume", "hits": 1}])
    assert [(g[0], g[1], g[3]) for g in groups] == [(UNROUTED, HTTP_GROUP, 8), ("order.created consume", ENTRY_POINT, 1)]


def test_strip_prefixes_splits_a_context_path():
    resources = [("GET /shop/api/cart/{id}", 5), ("GET /shop/api/orders", 3), ("GET /shop", 1),
                 ("GET /shopping-list", 2)]
    assert _names(resources) == [("Shop API", 9), ("Shopping-List API", 2)]
    assert _names(resources, strip_prefixes=("/shop",)) == [
        ("Cart API", 5), ("Orders API", 3), ("Shopping-List API", 2), ("Root API", 1)]
