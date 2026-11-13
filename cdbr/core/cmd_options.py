"""
cdbr.core.cmd_options

Option combinatorial hygiene checking (mock)

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import Protocol

from cdbr.core.exceptions import InvalidCmdOption


# ---------------------------------------------------------------------------
# Context protocol (avoids circular import)
# ---------------------------------------------------------------------------


class _CmdCtx(Protocol):

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
    def verbosity(self) -> int: ...

    @property
    def output(self) -> str: ...


# ---------------------------------------------------------------------------
# Modes (mock)
# ---------------------------------------------------------------------------


class CmdMode(Enum):
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


def mode_derive(ctx: _CmdCtx) -> CmdMode:
    """
    Derive a crude operational mode from CLI flags.
    """

    if ctx.list_:
        return CmdMode.LIST

    if ctx.patterns:
        return CmdMode.FILTER

    if ctx.luck:
        return CmdMode.LUCK

    return CmdMode.RENDER


# ---------------------------------------------------------------------------
# Validation (mock combinatorial hygiene)
# ---------------------------------------------------------------------------


def mode_validate(ctx: _CmdCtx, mode: CmdMode) -> None:
    """
    Very loose / illustrative validation rules.
    """

    # ---- list mode should be "pure"
    if mode == CmdMode.LIST:
        if ctx.patterns:
            raise InvalidCmdOption("--list cannot be combined with --pattern")
        if ctx.luck:
            raise InvalidCmdOption("--list cannot be combined with --luck")

    # ---- filter mode needs something to filter
    if mode == CmdMode.FILTER:
        if not ctx.patterns:
            raise InvalidCmdOption("filter mode requires at least one --pattern")

    # ---- luck mode is exclusive (because why not)
    if ctx.luck:
        if ctx.patterns:
            raise InvalidCmdOption("--luck cannot be combined with --pattern")
        if ctx.list_:
            raise InvalidCmdOption("--luck cannot be combined with --list")

    # ---- render mode sanity
    if mode == CmdMode.RENDER:
        if not ctx.output:
            raise InvalidCmdOption("render mode requires --output")

    # ---- path sanity (generic)
    if _flag_enabled(ctx.path) and not isinstance(ctx.path, Path):
        raise InvalidCmdOption("--path must be a directory path")

    # ---- verbosity sanity (just illustrative)
    if ctx.verbosity < 0:
        raise InvalidCmdOption("--verbose cannot be negative")
