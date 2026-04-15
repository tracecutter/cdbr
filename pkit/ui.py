"""
pkit.ui

UI facade for pkit.

This module re-exports Click (or rich-click) so that command
modules can simply:

    import pkit.ui as click

without caring which backend is in use.

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.

ALTERNATIVE RICH_CLICK

from rich_click import *   # noqa
"""

from click import *  # noqa
