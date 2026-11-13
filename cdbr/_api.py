"""
cdbr._api

Bootstrap API decorator registry.

This module provides the ``api`` decorator used to declare public API
entities in a project.  It intentionally lives in a minimal dependency
layer so that it can be imported by any module without introducing
circular import problems.

Design rule
-----------

This module must remain dependency-free with respect to the rest of
``cdbr``.  In particular it must **not** import:

    cdbr.core.*
    cdbr.api
    cdbr.docs_*

Only standard-library modules may be imported here.

Higher layers (for example ``cdbr.api``) extend the registry with
utilities for extracting documentation symbols from decorated objects.

Typical usage
-------------

Project code declares public API elements using the decorator:

    from cdbr import api

    @api(group="backend")
    class Backend:
        ...

The decorator records the object in an internal registry and ensures
that it is exported through the package namespace and ``__all__``.

Documentation systems can later inspect this registry to generate API
references such as:

    <project>-api(3)

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

import sys
import importlib
import pkgutil

from typing import Any
from collections.abc import Callable


class _API:
    """
    Registry for objects declared as part of a project's public API.
    """

    def __init__(self) -> None:
        self._registry: list[tuple[Any, dict[str, Any]]] = []

    # ---------------------------------------------------------
    # decorator
    # ---------------------------------------------------------

    def __call__(self, **meta) -> Callable:

        def decorator(obj: Any) -> Any:

            info = {
                "name": obj.__name__,
                "module": obj.__module__,
                "kind": "class" if isinstance(obj, type) else "function",
                **meta,
            }

            self._registry.append((obj, info))

            # ---- export object onto top-level package namespace

            package = obj.__module__.split(".", 1)[0]
            pkg = sys.modules.get(package)

            if pkg is not None:

                # expose object on package
                setattr(pkg, obj.__name__, obj)

                # maintain package __all__
                if not hasattr(pkg, "__all__"):
                    pkg.__all__ = []  # type: ignore[attr-defined]

                all_list = pkg.__all__  # type: ignore[attr-defined]

                if obj.__name__ not in all_list:
                    all_list.append(obj.__name__)

            return obj

        return decorator

    # ---------------------------------------------------------
    # discovery
    # ---------------------------------------------------------

    def discover(self, package: str) -> None:
        """Import all modules in a package to trigger decorators."""

        root = importlib.import_module(package)

        if not hasattr(root, "__path__"):
            return

        for mod in pkgutil.walk_packages(root.__path__, root.__name__ + "."):
            importlib.import_module(mod.name)


# singleton
api = _API()
