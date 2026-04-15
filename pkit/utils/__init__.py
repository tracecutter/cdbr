"""
pkit.utils.__init__

Curated public utility API for pkit.

This package exposes a small set of named subsystems and data structures used across pkit commands and workers.

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""

# Subsystems
from . import mark
from . import diff

# Context / data
from .mark import MarkContext

__all__ = [
    # SUBSYSTEMS
    "mark",
    "diff",
    # CONTEXT
    "MarkContext",
]
