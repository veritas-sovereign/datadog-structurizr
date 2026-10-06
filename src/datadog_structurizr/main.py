"""CLI entry point: Datadog APM service -> C4 L0/L1/L2 as Structurizr DSL and Mermaid."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .client import DatadogAPIError, fetch_all
from .config import load_config
from .emitter import (MODEL_FILE, VIEWS_FILE, emit_dsl_model, emit_dsl_views, emit_mermaid,
                      emit_workspace, inline_includes)
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
    cli.add_argument("--no-raw", action="store_true",
                     help="do not save the Datadog responses to <output>/raw/; they hold internal "
                          "service and route names, and --offline needs them")
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
            "NO_RAW": "1" if args.no_raw else None,
        },
        config_file=args.config,
        prompt=input if interactive else None,
    )
    source = cfg.raw_dir if cfg.offline else f"Datadog ({cfg.site})"

    print(f"[1/4] Fetching '{cfg.service}' (env={cfg.env}) from {source}...")
    try:
        fetched = fetch_all(cfg)
    except DatadogAPIError as exc:
        # Nothing is written, raw/ included: a diagram from partial data looks
        # right but is not.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not cfg.save_raw:
        print("      responses not saved (--no-raw)"
              + (f"; {cfg.raw_dir} is from an earlier run" if cfg.raw_dir.exists() else ""))
    deps, member_deps, resources = fetched.deps, fetched.member_deps, fetched.resources
    print(f"      calls={len(deps.get('calls') or [])} "
          f"called_by={len(deps.get('called_by') or [])} resources={len(resources)}"
          + (f" included={len(member_deps)}" if member_deps else ""))

    print("[2/4] Building C4 model...")
    model = build_model(deps, resources, fetched.definition, cfg, member_deps, fetched.types)
    for warning in model.warnings:
        print(f"      warning: {warning}")

    print("[3/4] Writing Structurizr DSL and Mermaid sources...")
    out = cfg.output_dir
    (out / MODEL_FILE).write_text(emit_dsl_model(model), encoding="utf-8")
    (out / VIEWS_FILE).write_text(emit_dsl_views(model), encoding="utf-8")
    dsl_path = out / "workspace.dsl"
    if not dsl_path.exists():
        dsl_path.write_text(emit_workspace(model), encoding="utf-8")
        print(f"      created {dsl_path.name}; it is yours to edit and is never overwritten")
    elif MODEL_FILE not in dsl_path.read_text(encoding="utf-8"):
        print(f"      warning: {dsl_path.name} does not !include {MODEL_FILE}, so it does not "
              "show this run. Add the includes, or delete it to have it created again.")
    inline_path = out / "workspace-inline.dsl"
    inline_path.write_text(inline_includes(dsl_path.read_text(encoding="utf-8"), out), encoding="utf-8")
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
    print(f"  DSL : {dsl_path} (includes {MODEL_FILE}, {VIEWS_FILE})")
    print(f"  DSL : {inline_path} (single file for the Structurizr playground)")
    for p in mmd_files:
        print(f"  MMD : {p}")
    for p in images:
        print(f"  IMG : {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
