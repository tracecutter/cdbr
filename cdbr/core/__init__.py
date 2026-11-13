"""
cdbr.core.__init__

Core domain logic for cdbr.

This package contains semantic operations over project configuration
(e.g. dependencies, versioning) and raises domain-level exceptions.

No CLI, no filesystem I/O.

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""

# Exceptions

from .exceptions import CdbrCoreError as CdbrCoreError
