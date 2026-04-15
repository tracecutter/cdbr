"""
pkit.cmds.__init__

Autodiscovery of pkit subcommands

INTERNAL

Usage:
    from pkit.cmds import discover

Examples:
    cmds = discover()
    cmds["bump"](...)

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

__all__ = ["discover"]

from importlib import import_module
from pkgutil import iter_modules

import pkit.ui as click


def discover() -> dict[str, click.Command]:
    cmds = {}

    for mod in iter_modules(__path__):
        if mod.ispkg or mod.name.startswith("_"):
            continue

        module = import_module(f"{__name__}.{mod.name}")

        cmd = getattr(module, "cmd", None)
        if cmd is not None:
            cmds[mod.name] = cmd

    return cmds
