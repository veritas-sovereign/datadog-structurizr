"""Configuration loading and validation.

Precedence, highest first: command-line flags, the --config TOML file,
environment variables (or a .env file). Datadog keys are only read from the
environment, never from the config file or the command line.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.9/3.10 in CI
    import tomli as tomllib

# Top-level and per-table keys accepted in the config file; anything else is a typo.
_FILE_SCHEMA: dict[str, Any] = {
    "service": str, "env": str, "hours": int, "site": str, "output": str,
    "ignore": list,
    "system": {"name": str, "description": str, "include": list},
    "person": {"enabled": bool, "name": str, "description": str},
    "classify": {"datastores": list, "external": list, "internal": list},
    "components": {"max": int, "strip_prefixes": list},
}
_SECRET_KEYS = {"api_key", "app_key", "dd_api_key", "dd_app_key", "api-key", "app-key"}


@dataclass(frozen=True)
class Config:
    api_key: str
    app_key: str
    site: str
    service: str
    env: str
    lookback_hours: int
    output_dir: Path
    offline: bool  # rebuild from output/raw/*.json instead of calling Datadog
    save_raw: bool = True  # False: keep the responses in memory only (--no-raw)
    # Model inputs. Names in include are exact; the other lists accept fnmatch globs.
    system_name: str = ""
    system_description: str = ""
    include: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    datastores: tuple[str, ...] = ()
    external: tuple[str, ...] = ()
    internal: tuple[str, ...] = ()
    person_enabled: bool = True
    person_name: str = "User"
    person_description: str = "End user of the web component."
    max_components: int = 12  # L2 keeps this many, the last one being "Other"
    strip_prefixes: tuple[str, ...] = ()  # path prefixes removed before grouping routes
    source_file: Optional[Path] = field(default=None, compare=False)

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw"


def _check_schema(data: dict[str, Any], schema: dict[str, Any], where: str) -> None:
    for key, value in data.items():
        if key.lower() in _SECRET_KEYS:
            raise SystemExit(f"{where}: '{key}' is not allowed here. "
                             "Put Datadog keys in DD_API_KEY / DD_APP_KEY environment variables.")
        if key not in schema:
            raise SystemExit(f"{where}: unknown key '{key}'. Allowed: {', '.join(schema)}.")
        expected = schema[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise SystemExit(f"{where}: '{key}' must be a table ([{key}]).")
            _check_schema(value, expected, f"{where} [{key}]")
        elif expected is list:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise SystemExit(f"{where}: '{key}' must be a list of strings.")
        elif not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise SystemExit(f"{where}: '{key}' must be {expected.__name__}.")


def read_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Config file not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{path}: invalid TOML: {exc}") from None
    _check_schema(data, _FILE_SCHEMA, str(path))
    return data


def normalize_site(site: str) -> str:
    """The Datadog site as the tool expects it ("datadoghq.eu"), from forms people
    copy from the browser or the API docs: "https://api.datadoghq.eu/" or
    "api.datadoghq.eu". The tool adds "https://api." itself."""
    site = site.strip().lower()
    for prefix in ("https://", "http://", "api.", "app."):
        site = site.removeprefix(prefix)
    return site.rstrip("/")


def load_config(overrides: dict[str, Any] | None = None,
                config_file: Path | None = None,
                prompt: Callable[[str], str] | None = None) -> Config:
    """Build the Config.

    overrides: command-line values (None means not given).
    prompt: asks for a missing service or env; pass None to never prompt.
    """
    # Only ./.env: without a path, load_dotenv searches upwards from this
    # module's folder, so an editable install would read the repository's .env.
    load_dotenv(Path.cwd() / ".env")
    cli = {k: v for k, v in (overrides or {}).items() if v not in (None, "", ())}
    file = read_config_file(config_file) if config_file else {}
    system, person, classify = file.get("system", {}), file.get("person", {}), file.get("classify", {})
    components = file.get("components", {})
    max_components = components.get("max", 12)
    if max_components < 2:
        raise SystemExit(f"{config_file}: [components] 'max' must be at least 2.")
    strip_prefixes = tuple(components.get("strip_prefixes", []))
    for prefix in strip_prefixes:
        if not prefix.startswith("/") or prefix == "/":
            raise SystemExit(f"{config_file}: [components] 'strip_prefixes' entries are paths "
                             f"such as \"/shop\", got {prefix!r}.")

    def get(cli_key: str, file_value: Any, env_key: str | None, default: Any = None) -> Any:
        if cli_key in cli:
            return cli[cli_key]
        if file_value is not None:
            return file_value
        if env_key and os.getenv(env_key):
            return os.getenv(env_key)
        return default

    offline = bool(cli.get("OFFLINE"))
    save_raw = not cli.get("NO_RAW")
    if offline and not save_raw:
        raise SystemExit("--no-raw cannot be used with --offline, which reads the saved responses.")
    service = get("DD_SERVICE", file.get("service"), "DD_SERVICE")
    env = get("DD_ENV", file.get("env"), "DD_ENV")
    if prompt:
        if not service:
            service = prompt("APM service name: ").strip()
        if not env:
            env = prompt("APM environment (for example prod): ").strip()

    api_key, app_key = os.getenv("DD_API_KEY", ""), os.getenv("DD_APP_KEY", "")
    missing = [name for name, value in (("DD_SERVICE", service), ("DD_ENV", env)) if not value]
    if not offline:
        missing += [name for name, value in (("DD_API_KEY", api_key), ("DD_APP_KEY", app_key)) if not value]
    if missing:
        raise SystemExit(
            f"Missing required settings: {', '.join(missing)}. "
            "Set them in the environment or .env (see .env.example); "
            "service and env can also come from --service/--env or the config file."
        )

    output_dir = Path(get("OUTPUT_DIR", file.get("output"), "OUTPUT_DIR", "output"))
    (output_dir / "raw" if save_raw else output_dir).mkdir(parents=True, exist_ok=True)

    include = [*system.get("include", []), *cli.get("INCLUDE", ())]
    return Config(
        api_key=api_key,
        app_key=app_key,
        site=normalize_site(get("DD_SITE", file.get("site"), "DD_SITE", "datadoghq.com")),
        service=service,
        env=env,
        lookback_hours=int(get("DD_LOOKBACK_HOURS", file.get("hours"), "DD_LOOKBACK_HOURS", 24)),
        output_dir=output_dir,
        offline=offline,
        save_raw=save_raw,
        system_name=get("SYSTEM_NAME", system.get("name"), None, ""),
        system_description=system.get("description", ""),
        include=tuple(dict.fromkeys(n for n in include if n != service)),
        ignore=tuple(file.get("ignore", [])),
        datastores=tuple(classify.get("datastores", [])),
        external=tuple(classify.get("external", [])),
        internal=tuple(classify.get("internal", [])),
        person_enabled="NO_PERSON" not in cli and person.get("enabled", True),
        person_name=person.get("name", "User"),
        person_description=person.get("description", "End user of the web component."),
        max_components=max_components,
        strip_prefixes=strip_prefixes,
        source_file=config_file,
    )
