"""Lightweight C4 model dataclasses.

Only the subset needed for the three views:
  L0 System Context  - person, target system, neighbouring systems
  L1 Container       - containers inside the target system
  L2 Component       - components inside the target container
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ElementKind = Literal["person", "system", "container", "component"]


@dataclass(frozen=True)
class Evidence:
    """Where an element or relationship came from: the Datadog call that returned it
    (named by the API call, not a file, so it holds with --no-raw too), or
    "assumption" for what the tool draws without Datadog data."""
    source: str
    detail: str


def _add(evidence: list[Evidence], source: str, detail: str) -> None:
    item = Evidence(source, detail)
    if item not in evidence:
        evidence.append(item)


@dataclass
class Element:
    key: str                    # unique identifier (letters, digits, underscore)
    name: str
    kind: ElementKind
    description: str = ""
    technology: str = ""
    external: bool = False      # outside the organisation (SaaS, cloud API)
    database: bool = False      # rendered with the datastore shape
    parent_key: str | None = None
    basis: str = ""             # why a dependency got its kind: config, span type or name hint
    children: list[Element] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def cite(self, source: str, detail: str) -> None:
        _add(self.evidence, source, detail)


@dataclass
class Relationship:
    source_key: str
    target_key: str
    description: str = ""
    technology: str = ""
    evidence: list[Evidence] = field(default_factory=list)

    def cite(self, source: str, detail: str) -> None:
        _add(self.evidence, source, detail)


@dataclass
class C4Model:
    name: str
    description: str
    person: Element | None  # None when the person is turned off
    target_system: Element
    target_container: Element
    systems: list[Element] = field(default_factory=list)   # neighbours, not the target
    relationships: list[Relationship] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # printed by the CLI, not drawn

    def relate(self, source: str, target: str, description: str, technology: str = "") -> Relationship | None:
        """The relationship from source to target, added on first sight; None for a self-call."""
        if source == target:  # a service calling itself is not an architectural edge
            return None
        for r in self.relationships:
            if r.source_key == source and r.target_key == target:
                return r
        r = Relationship(source, target, description, technology)
        self.relationships.append(r)
        return r

    def all_elements(self) -> list[Element]:
        out = [e for e in (self.person, self.target_system) if e] + self.systems
        for c in self.target_system.children:
            out.append(c)
            out.extend(c.children)
        return out
