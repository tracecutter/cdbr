"""
cdbr.context

Semantic command context types for cdbr.

This module defines immutable context classes that represent the
fully-resolved intent of a cdbr command invocation, independent of
how that intent was expressed (CLI, tests, or replay).

`CdbrContext` is the common base for all cdbr command contexts and
defines truly global execution concerns (e.g. quiet/verbose).

Concrete command contexts subclass `CdbrContext` and live with their
respective command implementations.

It is safe to import from command modules without side-effects.

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from npkglib import toml_io as toml
from npkglib import mark


T = TypeVar("T", bound="CdbrContext")

_current_context: CdbrContext | None = None


# ---------------------------------------------------------------------------
# Cdbr CLI derived execution Context and Mode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CdbrMode:
    """
    Resolved execution mode for cdbr.

    Represents how the CLI operates, independent of where the inputs
    originated (CLI flags, environment, config, etc).
    """

    quiet: bool = False
    emoji: bool = False
    verbose: bool = False
    diff: str = "2up"


@dataclass(frozen=True, kw_only=True)
class CdbrContext:
    """
    Global CLI execution context.

    Immutable and shared across command contexts.
    """

    mode: CdbrMode

    def extend(self, cls: type[T], **kwargs) -> T:
        """
        Create a derived command-specific context from this base context.
        """
        data = vars(self).copy()
        data.update(kwargs)
        return cls(**data)

    def __post_init__(self) -> None:
        global _current_context
        _current_context = self


# ------------------------------------------------------------------
# Context Bootstrap Helpers
# ------------------------------------------------------------------


def _distribution_name_from_doc(doc: toml.TOMLDocument) -> str:

    distribution_name = toml.get_by_dotted_key(doc, "project.name")

    if not distribution_name:
        raise ValueError("pyproject.toml missing [project].name")

    return distribution_name


def _invocation_name_from_doc(doc: toml.TOMLDocument) -> str | None:

    scripts = doc.get("project", {}).get("scripts", {})

    if not scripts:
        return None

    invocation_name = next(iter(scripts.keys()))

    if len(scripts) > 1:
        mark.warn(f"Multiple project scripts found; using '{invocation_name}' as canonical invocation")

    return invocation_name


def _project_name_from_doc(doc: toml.TOMLDocument) -> str:

    invocation_name = _invocation_name_from_doc(doc)

    if invocation_name:
        return invocation_name

    return _distribution_name_from_doc(doc)


# ---------------------------------------------------------------------------
# Context Access Helpers
# ---------------------------------------------------------------------------


def current_get() -> CdbrContext:
    if _current_context is None:
        raise RuntimeError("cdbr context has not been initialized")
    return _current_context
