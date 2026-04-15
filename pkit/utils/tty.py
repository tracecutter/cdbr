"""
pkit.utils.tty

Return terminal width when stdout is a TTY; otherwise return None.

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

import sys
import shutil

_UNBOUNDED = 12345


def stdout_width(default: int = 120) -> int:
    if not sys.stdout.isatty():
        return _UNBOUNDED

    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return default
