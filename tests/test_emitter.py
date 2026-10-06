from datadog_structurizr.emitter import (emit_dsl_model, emit_dsl_views, emit_mermaid, emit_workspace,
                                        inline_includes)
from datadog_structurizr.mapper import build_model


def _model(cfg):
    return build_model(
        {"calls": ["cart-service", "orders-postgres", "stripe-api"], "called_by": ["api-gateway"]},
        [{"resource": "GET /api/cart", "hits": 3}, {"resource": "nightly.job", "hits": 1}],
        {}, cfg,
    )


def test_dsl_nests_containers_and_components(offline_cfg):
    dsl = emit_dsl_model(_model(offline_cfg))
    system = dsl.index("checkout_web_system = softwareSystem")
    container = dsl.index("checkout_web = container")
    component = dsl.index("checkout_web__Cart_API = component")
    assert system < container < component
    assert 'orders_postgres = container "orders-postgres"' in dsl
    assert 'stripe_api = softwareSystem "stripe-api" "External service." "External"' in dsl


def test_dsl_defines_three_views_without_remote_theme(offline_cfg):
    dsl = emit_dsl_views(_model(offline_cfg))
    assert 'systemContext checkout_web_system "L0-SystemContext"' in dsl
    assert 'container checkout_web_system "L1-Containers"' in dsl
    assert 'component checkout_web "L2-Components" "Entry points of checkout-web' in dsl
    assert "not its code structure" in dsl
    assert "theme" not in dsl


def test_dsl_escapes_quotes(offline_cfg):
    m = _model(offline_cfg)
    m.target_system.description = 'say "hi"'
    assert "\"say 'hi'\"" in emit_dsl_model(m)


def test_mermaid_l0_collapses_containers_into_system(offline_cfg):
    l0 = emit_mermaid(_model(offline_cfg))["L0-SystemContext"]
    assert "Rel(checkout_web_system, cart_service" in l0
    assert "Rel(api_gateway, checkout_web_system" in l0
    assert "orders_postgres" not in l0          # owned datastore is inside the system
    assert "System_Ext(stripe_api" in l0


def test_mermaid_l1_shows_datastore_inside_boundary(offline_cfg):
    l1 = emit_mermaid(_model(offline_cfg))["L1-Containers"]
    boundary = l1[l1.index("System_Boundary("):l1.index("    }")]
    assert "ContainerDb(orders_postgres" in boundary
    assert "Rel(checkout_web, orders_postgres" in l1


def test_mermaid_l2_only_includes_related_elements(offline_cfg):
    l2 = emit_mermaid(_model(offline_cfg))["L2-Components"]
    assert "Component(checkout_web__Cart_API" in l2
    assert "Component(checkout_web__nightly_job" in l2
    assert "Rel(user, checkout_web__Cart_API" in l2
    assert "cart_service" not in l2


def test_no_person_emits_no_person_anywhere(offline_cfg):
    import dataclasses
    cfg = dataclasses.replace(offline_cfg, person_enabled=False)
    m = _model(cfg)
    assert " = person " not in emit_dsl_model(m)
    for text in emit_mermaid(m).values():
        assert "Person(" not in text
    assert "Rel(api_gateway, checkout_web__Cart_API" in emit_mermaid(m)["L2-Components"]


def test_included_container_drawn_in_l1_and_collapsed_in_l0(offline_cfg):
    import dataclasses
    cfg = dataclasses.replace(offline_cfg, include=("checkout-worker",))
    m = build_model({"calls": ["checkout-worker"]}, [], {}, cfg,
                    {"checkout-worker": {"calls": ["billing-service"]}})
    views = emit_mermaid(m)
    assert "Container(checkout_worker" in views["L1-Containers"]
    assert "Rel(checkout_web, checkout_worker" in views["L1-Containers"]
    assert "checkout_worker" not in views["L0-SystemContext"]
    assert "Rel(checkout_web_system, billing_service" in views["L0-SystemContext"]
    assert 'checkout_worker = container "checkout-worker"' in emit_dsl_model(m)


def test_workspace_includes_fragments_and_suggests_a_relationship(offline_cfg):
    ws = emit_workspace(_model(offline_cfg))
    model_block, views_block = ws.index("model {"), ws.index("views {")
    assert model_block < ws.index("!include datadog-model.dsl") < views_block < ws.index("!include datadog-views.dsl")
    assert '# checkout_web__Cart_API -> cart_service "Calls"' in ws


def test_inline_includes_pastes_only_generated_fragments(tmp_path):
    (tmp_path / "datadog-model.dsl").write_text("a = person \"A\"\n")
    (tmp_path / "datadog-views.dsl").write_text("styles {\n}\n")
    ws = ("workspace {\n    model {\n        !include datadog-model.dsl\n        !include mine.dsl\n"
          "    }\n    views {\n        !include datadog-views.dsl\n    }\n}\n")
    flat = inline_includes(ws, tmp_path)
    assert '        a = person "A"' in flat
    assert "        styles {\n        }" in flat
    assert "!include mine.dsl" in flat and "!include datadog" not in flat


def test_dsl_writes_the_classification_reason_as_a_property(offline_cfg):
    dsl = emit_dsl_model(_model(offline_cfg))
    assert ('stripe_api = softwareSystem "stripe-api" "External service." "External" {\n'
            '    properties {\n'
            '        "Classified by" "name hint stripe"\n'
            '    }\n'
            '}\n') in dsl
    assert ('        tags "Database"\n'
            '        properties {\n'
            '            "Classified by" "name hint postgres"\n') in dsl
    # The target container has no basis, so its first child line follows its opening line.
    assert ('checkout_web = container "checkout-web" "Application container." "APM service" {\n'
            '        checkout_web__') in dsl
