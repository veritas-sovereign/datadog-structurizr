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
    children: list["Element"] = field(default_factory=list)


@dataclass
class Relationship:
    source_key: str
    target_key: str
    description: str = ""
    technology: str = ""


@dataclass
class C4Model:
    name: str
    description: str
    person: Element | None  # None when the person is turned off
    target_system: Element
    target_container: Element
    systems: list[Element] = field(default_factory=list)   # neighbours, not the target
    relationships: list[Relationship] = field(default_factory=list)

    def relate(self, source: str, target: str, description: str, technology: str = "") -> None:
        if source == target:  # a service calling itself is not an architectural edge
            return
        if not any(r.source_key == source and r.target_key == target for r in self.relationships):
            self.relationships.append(Relationship(source, target, description, technology))

    def all_elements(self) -> list[Element]:
        out = [e for e in (self.person, self.target_system) if e] + self.systems
        for c in self.target_system.children:
            out.append(c)
            out.extend(c.children)
        return out
