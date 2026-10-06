"""End to end: the checked-in raw responses through the CLI, offline."""
from datadog_structurizr.main import main


def test_offline_run_writes_dsl_and_three_mermaid_views(checkout_dir):
    rc = main(["--service", "checkout-web", "--env", "prod", "--offline",
               "-o", str(checkout_dir), "--no-render"])
    assert rc == 0
    assert (checkout_dir / "workspace.dsl").stat().st_size > 0
    for view, header in (("L0-SystemContext", "C4Context"),
                         ("L1-Containers", "C4Container"),
                         ("L2-Components", "C4Component")):
        assert (checkout_dir / f"{view}.mmd").read_text().startswith(header)


def test_offline_run_is_deterministic(checkout_dir):
    args = ["--service", "checkout-web", "--env", "prod", "--offline", "-o", str(checkout_dir), "--no-render"]
    main(args)
    first = (checkout_dir / "workspace.dsl").read_text()
    main(args)
    assert (checkout_dir / "workspace.dsl").read_text() == first


def test_offline_without_raw_files_exits(tmp_path):
    import pytest
    with pytest.raises(SystemExit, match="not found"):
        main(["--service", "x", "--env", "prod", "--offline", "-o", str(tmp_path / "empty"), "--no-render"])


def test_example_config_file(checkout_dir):
    rc = main(["--config", str(checkout_dir / "c4.toml"), "--offline", "-o", str(checkout_dir), "--no-render"])
    assert rc == 0
    dsl = (checkout_dir / "workspace.dsl").read_text()
    assert 'Checkout_system = softwareSystem "Checkout"' in dsl
    assert 'user = person "Shopper"' in dsl
    assert 'checkout_worker = container "checkout-worker"' in dsl
    assert 'ledger = container "ledger"' in dsl and "otel" not in dsl
    l1 = (checkout_dir / "L1-Containers.mmd").read_text()
    assert "Rel(checkout_worker, aws_sqs" in l1


def test_include_flag_and_no_person(checkout_dir):
    main(["--service", "checkout-web", "--env", "prod", "--include", "checkout-worker", "--no-person",
          "--system-name", "Checkout", "--offline", "-o", str(checkout_dir), "--no-render"])
    dsl = (checkout_dir / "workspace.dsl").read_text()
    assert "checkout_worker = container" in dsl
    assert " = person " not in dsl


def test_no_prompt_without_terminal(tmp_path, monkeypatch):
    import io
    import pytest
    monkeypatch.setattr("sys.stdin", io.StringIO("web\nprod\n"))
    with pytest.raises(SystemExit, match="DD_SERVICE"):
        main(["--offline", "-o", str(tmp_path / "o"), "--no-render"])
