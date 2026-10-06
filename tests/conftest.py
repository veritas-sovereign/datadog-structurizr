import shutil
from pathlib import Path

import pytest

from datadog_structurizr.config import load_config

EXAMPLES = Path(__file__).parent.parent / "examples"
DD_VARS = ("DD_API_KEY", "DD_APP_KEY", "DD_SITE", "DD_SERVICE", "DD_ENV",
           "DD_LOOKBACK_HOURS", "OUTPUT_DIR")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No real credentials or .env file can leak into a test."""
    for name in DD_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def checkout_dir(tmp_path):
    """A copy of examples/checkout-web (c4.toml and raw responses) to write output into."""
    out = tmp_path / "out"
    shutil.copytree(EXAMPLES / "checkout-web", out,
                    ignore=shutil.ignore_patterns("*.dsl", "*.mmd", "*.svg", "plantuml"))
    return out


@pytest.fixture
def online_cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    return load_config({"DD_SERVICE": "checkout-web", "DD_ENV": "prod",
                        "OUTPUT_DIR": str(tmp_path / "out")})


@pytest.fixture
def offline_cfg(checkout_dir):
    return load_config({"DD_SERVICE": "checkout-web", "DD_ENV": "prod",
                        "OUTPUT_DIR": str(checkout_dir), "OFFLINE": "1"})
