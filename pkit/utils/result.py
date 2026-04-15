"""
pkit.utils.result

Place holder for result functions for pkit.

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


ResultMode = Literal["nominal", "proof", "diff", "null"]


@dataclass
class ResultContext:
    mode: ResultMode = "nominal"


_ctx: ResultContext = ResultContext()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure(ctx: ResultContext) -> None:
    """
    Configure the emission context.

    Commands are responsible for translating user intent
    (flags such as --dry-run, --diff, --check) into emit_mode.
    """
    global _ctx
    _ctx = ctx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def text(msg: str = "") -> None:
    """
    Result primary payload text.

    Suppressed entirely when emit_mode is 'null'.
    """
    if _ctx.mode == "null":
        return

    print(msg, file=sys.stdout)
