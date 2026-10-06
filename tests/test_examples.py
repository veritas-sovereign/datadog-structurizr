"""End to end: the checked-in raw responses through the CLI, offline."""
from datadog_structurizr.main import main


def test_offline_run_writes_dsl_and_three_mermaid_views(checkout_dir):
    rc = main(["--service", "checkout-web", "--env", "prod", "--offline",
               "-o", str(checkout_dir), "--no-render"])
    assert rc == 0
    for name in ("workspace.dsl", "datadog-model.dsl", "datadog-views.dsl", "workspace-inline.dsl"):
        assert (checkout_dir / name).stat().st_size > 0
    for view, header in (("L0-SystemContext", "C4Context"),
                         ("L1-Containers", "C4Container"),
                         ("L2-Components", "C4Component")):
        assert (checkout_dir / f"{view}.mmd").read_text().startswith(header)


def test_offline_run_is_deterministic(checkout_dir):
    args = ["--service", "checkout-web", "--env", "prod", "--offline", "-o", str(checkout_dir), "--no-render"]
    main(args)
    first = (checkout_dir / "datadog-model.dsl").read_text()
    main(args)
    assert (checkout_dir / "datadog-model.dsl").read_text() == first


def test_rerun_keeps_hand_edits_in_workspace(checkout_dir):
    args = ["--service", "checkout-web", "--env", "prod", "--offline", "-o", str(checkout_dir), "--no-render"]
    main(args)
    ws = checkout_dir / "workspace.dsl"
    edit = '        checkout_web__Cart_API -> cart_service "Reads cart"\n'
    ws.write_text(ws.read_text().replace("    }\n\n    views", edit + "    }\n\n    views"))
    main(args)
    assert edit in ws.read_text()
    inline = (checkout_dir / "workspace-inline.dsl").read_text()
    assert edit in inline and 'checkout_web = container "checkout-web"' in inline
    assert "!include" not in inline


def test_workspace_without_includes_is_kept_with_warning(checkout_dir, capsys):
    (checkout_dir / "workspace.dsl").write_text("workspace {\n}\n")
    main(["--service", "checkout-web", "--env", "prod", "--offline", "-o", str(checkout_dir), "--no-render"])
    assert (checkout_dir / "workspace.dsl").read_text() == "workspace {\n}\n"
    assert "does not !include datadog-model.dsl" in capsys.readouterr().out


def test_offline_without_raw_files_exits(tmp_path):
    import pytest
    with pytest.raises(SystemExit, match="not found"):
        main(["--service", "x", "--env", "prod", "--offline", "-o", str(tmp_path / "empty"), "--no-render"])


def test_example_config_file(checkout_dir):
    rc = main(["--config", str(checkout_dir / "c4.toml"), "--offline", "-o", str(checkout_dir), "--no-render"])
    assert rc == 0
    dsl = (checkout_dir / "datadog-model.dsl").read_text()
    assert 'Checkout_system = softwareSystem "Checkout"' in dsl
    assert 'user = person "Shopper"' in dsl
    assert 'checkout_worker = container "checkout-worker"' in dsl
    assert 'ledger = container "ledger"' in dsl and "otel" not in dsl
    l1 = (checkout_dir / "L1-Containers.mmd").read_text()
    assert "Rel(checkout_worker, aws_sqs" in l1


def test_include_flag_and_no_person(checkout_dir):
    main(["--service", "checkout-web", "--env", "prod", "--include", "checkout-worker", "--no-person",
          "--system-name", "Checkout", "--offline", "-o", str(checkout_dir), "--no-render"])
    dsl = (checkout_dir / "datadog-model.dsl").read_text()
    assert "checkout_worker = container" in dsl
    assert " = person " not in dsl


def test_no_prompt_without_terminal(tmp_path, monkeypatch):
    import io
    import pytest
    monkeypatch.setattr("sys.stdin", io.StringIO("web\nprod\n"))
    with pytest.raises(SystemExit, match="DD_SERVICE"):
        main(["--offline", "-o", str(tmp_path / "o"), "--no-render"])


def test_api_error_exits_non_zero_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from datadog_structurizr import client

    class Forbidden:
        status_code, text = 403, '{"errors": ["Forbidden"]}'

    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: Forbidden())
    out = tmp_path / "o"
    rc = main(["--service", "web", "--env", "prod", "-o", str(out), "--no-render", "--no-input"])
    assert rc == 1
    assert "403" in capsys.readouterr().err
    assert not (out / "workspace.dsl").exists()
