"""
cdbr.api

Declarative public API support for cdbr.

[[api.overview]]

The API subsystem allows source code to declare public interface
elements using the ``api`` decorator:

    from cdbr import api

    @api()
    def my_function():
        ...

In ``cdbr``, the decorator is backed by a small registry implemented in
``cdbr._api``.  Decorated objects are recorded along with lightweight
metadata and are exported onto the package namespace.

Currently provided
------------------

The bootstrap API layer currently supports:

\b
- declaration of public API entities via ``@api(...)``
- registry of decorated objects and associated metadata
- export of decorated objects onto the package namespace
- maintenance of the package ``__all__`` list
- optional package discovery via module import walking

This keeps public API declaration close to the code that implements it,
while remaining dependency-light and safe to import broadly.

[[api.design]]

The longer-term design is for the API subsystem to serve as a source of
structured information for documentation generation.

In that fuller model, decorated classes and functions may later be
translated into documentation symbols describing things such as:

\b
- entity kind
- defining module
- optional grouping metadata
- summary text from docstrings
- selected public member metadata for classes

That extraction layer and its documentation backends are not yet
implemented here.  ``cdbr.api`` currently provides the declarative
registry layer only.

[[api.example]]

Example:

```code
    from cdbr import api

    @api(group="example")
    def example():
        '''
        Minimal example API entity.
        '''
```

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations  # noqa: F401

from cdbr._api import api


@api(group="example")
def example() -> None:
    """
    Minimal example API entity.
    """
    return


all = [
    "api",
    "example",
]
