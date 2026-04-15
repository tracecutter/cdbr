"""
pkit.context

Semantic command context types for pkit.

This module defines immutable context classes that represent the
fully-resolved intent of a pkit command invocation, independent of
how that intent was expressed (CLI, tests, or replay).

`PkitContext` is the common base for all pkit command contexts and
defines truly global execution concerns (e.g. quiet/verbose).

Concrete command contexts subclass `PkitContext` and live with their
respective command implementations.

It is safe to import from command modules without side-effects.

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar


T = TypeVar("T", bound="PkitContext")


# ---------------------------------------------------------------------------
# Pkit CLI derived execution Context and Mode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PkitMode:
    """
    Resolved execution mode for pkit.

    Represents how the CLI operates, independent of where the inputs
    originated (CLI flags, environment, config, etc).
    """

    quiet: bool = False
    emoji: bool = False
    verbose: bool = False
    diff: str = "2up"


@dataclass(frozen=True, kw_only=True)
class PkitContext:
    """
    Global CLI execution context.

    Immutable and shared across command contexts.
    """

    mode: PkitMode

    def extend(self, cls: type[T], **kwargs) -> T:
        """
        Create a derived command-specific context from this base context.
        """
        data = vars(self).copy()
        data.update(kwargs)
        return cls(**data)
