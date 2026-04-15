"""
pkit.core.sub_options

Option combinatorial hygiene checking (mock)

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import Protocol

from pkit.core.exceptions import InvalidSubOption


# ---------------------------------------------------------------------------
# Context protocol (avoids circular import)
# ---------------------------------------------------------------------------


class _SubCtx(Protocol):

    @property
    def args(self) -> tuple[str, ...]: ...

    @property
    def dry_run(self) -> bool: ...

    @property
    def path(self) -> Path | None: ...

    @property
    def name(self) -> str | None: ...

    @property
    def list_(self) -> bool: ...

    @property
    def patterns(self) -> tuple[str, ...]: ...

    @property
    def luck(self) -> bool: ...

    @property
    def submode(self) -> str | None: ...

    @property
    def verbose(self) -> int: ...

    @property
    def output(self) -> str: ...


# ---------------------------------------------------------------------------
# Modes (mock)
# ---------------------------------------------------------------------------


class SubMode(Enum):
    LIST = auto()
    FILTER = auto()
    LUCK = auto()
    RENDER = auto()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag_enabled(value) -> bool:
    return value not in (None, False, (), "")


# ---------------------------------------------------------------------------
# Mode derivation
# ---------------------------------------------------------------------------


def mode_derive(ctx: _SubCtx) -> SubMode:
    """
    Derive a crude operational mode from CLI flags.
    """

    if ctx.list_:
        return SubMode.LIST

    if ctx.patterns:
        return SubMode.FILTER

    if ctx.luck:
        return SubMode.LUCK

    return SubMode.RENDER


# ---------------------------------------------------------------------------
# Validation (mock combinatorial hygiene)
# ---------------------------------------------------------------------------


def mode_validate(ctx: _SubCtx, mode: SubMode) -> None:
    """
    Very loose / illustrative validation rules.
    """

    # ---- list mode should be "pure"
    if mode == SubMode.LIST:
        if ctx.patterns:
            raise InvalidSubOption("--list cannot be combined with --pattern")
        if ctx.luck:
            raise InvalidSubOption("--list cannot be combined with --luck")

    # ---- filter mode needs something to filter
    if mode == SubMode.FILTER:
        if not ctx.patterns:
            raise InvalidSubOption("filter mode requires at least one --pattern")

    # ---- luck mode is exclusive (because why not)
    if ctx.luck:
        if ctx.patterns:
            raise InvalidSubOption("--luck cannot be combined with --pattern")
        if ctx.list_:
            raise InvalidSubOption("--luck cannot be combined with --list")

    # ---- render mode sanity
    if mode == SubMode.RENDER:
        if not ctx.output:
            raise InvalidSubOption("render mode requires --output")

    # ---- path sanity (generic)
    if _flag_enabled(ctx.path) and not isinstance(ctx.path, Path):
        raise InvalidSubOption("--path must be a directory path")

    # ---- verbosity sanity (just illustrative)
    if ctx.verbose < 0:
        raise InvalidSubOption("--verbose cannot be negative")
