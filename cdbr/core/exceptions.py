"""
cdbr.core.exceptions

Core exceptions for cdbr.

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""


class CdbrCoreError(Exception):
    """Base class for all cdbr core/domain errors."""


# ---------------------------------------------------------------------------
# Example cmd errors
# ---------------------------------------------------------------------------


class CdbrCmdError(CdbrCoreError):
    """Base class for documentation-related errors."""


class InvalidCmdOption(CdbrCmdError):
    """Invalid command option combination."""
