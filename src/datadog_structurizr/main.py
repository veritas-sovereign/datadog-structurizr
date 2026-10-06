"""CLI entry point: Datadog APM service -> C4 L0/L1/L2 as Structurizr DSL and Mermaid."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .client import fetch_resources, fetch_service_definition, fetch_service_dependencies
from .config import load_config
from .emitter import emit_dsl, emit_mermaid
from .mapper import build_model
from .render import render_mermaid, render_structurizr


def _names(value: str) -> list[str]:
    return [n.strip() for n in value.split(",") if n.strip()]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    cli = argparse.ArgumentParser(
        prog="datadog-structurizr",
        description="Generate C4 system context, container and component diagrams "
                    "for one Datadog APM service.",
    )
    cli.add_argument("-c", "--config", type=Path,
                     help="TOML file with the service, system boundary, classification and person "
                          "(see examples/checkout-web/c4.toml)")
    cli.add_argument("--service", help="APM service name (overrides the config file and DD_SERVICE)")
    cli.add_argument("--env", help="APM environment; required by the API (overrides the config file and DD_ENV)")
    cli.add_argument("--hours", help="lookback window in hours (default 24)")
    cli.add_argument("-o", "--output", help="output directory (default output)")
    cli.add_argument("--system-name", help="name of the software system (default: the service name)")
    cli.add_argument("--include", action="append", type=_names, default=[], metavar="SERVICE[,SERVICE]",
                     help="other APM services that are containers of the same system; repeatable")
    cli.add_argument("--no-person", action="store_true",
                     help="draw no person; for services only called by other services")
    cli.add_argument("--offline", action="store_true",
                     help="rebuild from <output>/raw/*.json instead of calling Datadog")
    cli.add_argument("--no-render", action="store_true",
                     help="write .dsl and .mmd sources only; do not render images")
    cli.add_argument("--no-input", action="store_true",
                     help="never prompt for a missing service or env (prompts only happen on a terminal)")
    cli.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return cli.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    interactive = sys.stdin.isatty() and not args.no_input
    cfg = load_config(
        {
            "DD_SERVICE": args.service, "DD_ENV": args.env,
            "DD_LOOKBACK_HOURS": args.hours, "OUTPUT_DIR": args.output,
            "SYSTEM_NAME": args.system_name,
            "INCLUDE": tuple(n for group in args.include for n in group),
            "NO_PERSON": "1" if args.no_person else None,
            "OFFLINE": "1" if args.offline else None,
        },
        config_file=args.config,
        prompt=input if interactive else None,
    )
    source = cfg.raw_dir if cfg.offline else f"Datadog ({cfg.site})"

    print(f"[1/4] Fetching '{cfg.service}' (env={cfg.env}) from {source}...")
    deps = fetch_service_dependencies(cfg)
    member_deps = {name: fetch_service_dependencies(cfg, name) for name in cfg.include}
    resources = fetch_resources(cfg)
    definition = fetch_service_definition(cfg)
    print(f"      calls={len(deps.get('calls') or [])} "
          f"called_by={len(deps.get('called_by') or [])} resources={len(resources)}"
          + (f" included={len(member_deps)}" if member_deps else ""))

    print("[2/4] Building C4 model...")
    model = build_model(deps, resources, definition, cfg, member_deps)

    print("[3/4] Writing Structurizr DSL and Mermaid sources...")
    dsl_path = cfg.output_dir / "workspace.dsl"
    dsl_path.write_text(emit_dsl(model), encoding="utf-8")
    mmd_files = []
    for view, text in emit_mermaid(model).items():
        path = cfg.output_dir / f"{view}.mmd"
        path.write_text(text, encoding="utf-8")
        mmd_files.append(path)

    images = []
    if args.no_render:
        print("[4/4] Rendering skipped (--no-render)")
    else:
        print("[4/4] Rendering images...")
        images = render_mermaid(mmd_files) + render_structurizr(dsl_path, cfg.output_dir)

    print("\nDone. Outputs:")
    print(f"  DSL : {dsl_path}")
    for p in mmd_files:
        print(f"  MMD : {p}")
    for p in images:
        print(f"  IMG : {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
