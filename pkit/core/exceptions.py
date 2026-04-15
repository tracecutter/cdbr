"""
pkit.core.exceptions

Core exceptions for pkit.

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""


class PkitCoreError(Exception):
    """Base class for all pkit core/domain errors."""


# ---------------------------------------------------------------------------
# Example subcmd errors
# ---------------------------------------------------------------------------


class PkitSubError(PkitCoreError):
    """Base class for documentation-related errors."""


class InvalidSubOption(PkitSubError):
    """Invalid subcmd command option combination."""
