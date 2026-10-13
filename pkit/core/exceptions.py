"""
pkit.core.exceptions

Core exceptions for pkit.

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""


class PkitCoreError(Exception):
    """Base class for all pkit core/domain errors."""


# ---------------------------------------------------------------------------
# Example cmd errors
# ---------------------------------------------------------------------------


class PkitCmdError(PkitCoreError):
    """Base class for documentation-related errors."""


class InvalidCmdOption(PkitCmdError):
    """Invalid command option combination."""
