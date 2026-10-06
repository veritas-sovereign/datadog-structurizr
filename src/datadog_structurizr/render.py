"""Render diagrams.

Mermaid (mmdc) is the default path - no Java needed. structurizr-cli +
plantuml is used only when both are on PATH, as an alternative rendering of
workspace.dsl.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def render_mermaid(mmd_files: list[Path], fmt: str = "svg") -> list[Path]:
    if shutil.which("mmdc") is None:
        print("      mmdc not found - skipping image render "
              "(npm i -g @mermaid-js/mermaid-cli). .mmd sources still written.")
        return []
    out = []
    for src in mmd_files:
        dst = src.with_suffix(f".{fmt}")
        subprocess.run(["mmdc", "-q", "-i", str(src), "-o", str(dst)], check=True)
        out.append(dst)
    return out


def render_structurizr(dsl_path: Path, output_dir: Path, fmt: str = "svg") -> list[Path]:
    if not (shutil.which("structurizr-cli") and shutil.which("plantuml")):
        return []
    puml_dir = output_dir / "plantuml"
    puml_dir.mkdir(exist_ok=True)
    subprocess.run(
        ["structurizr-cli", "export", "-w", str(dsl_path), "-f", "plantuml", "-o", str(puml_dir)],
        check=True,
    )
    pumls = sorted(puml_dir.glob("*.puml"))
    if pumls:
        subprocess.run(["plantuml", f"-t{fmt}", *map(str, pumls)], check=True)
    return [p.with_suffix(f".{fmt}") for p in pumls]
