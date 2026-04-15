"""
pkit.__init__

Core library for the pkit project inspection and documentation tool.

This package contains the reusable machinery behind the pkit CLI.
It is safe to import and performs no I/O or command execution.

All CLI behavior lives outside this module.

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved.
:license: PROPRIETARY, see LICENSE for details.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pkit")
except PackageNotFoundError as e:
    raise RuntimeError(
        "pkit is being executed without being installed as a package.\n"
        "This is not supported. Install pkit properly (pipx, pip, editable install)."
    ) from e
