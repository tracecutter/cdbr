A **Renderer** defines *how a single documentation artifact* (README,
manpage, etc.) is produced.

A renderer instance represents **exactly one output artifact**, rendered from
one template, using one authoritative symbol table.

Renderers are normal Python classes that subclass ``Renderer``. They are
not discovered directly. Instead, they are instantiated by **backend modules**,
which control how many renderers exist and which artifacts are produced.

Conceptual Model
----------------

- A **Backend** decides *what* documentation artifacts exist.
- A **Renderer** decides *how* one artifact is rendered.
- A **Template** provides the static structure of the artifact.

Backends may create one or many renderer instances. Each renderer produces
exactly one output.

Renderer Responsibilities
-------------------------

Each renderer instance is responsible for:

- loading a single template
- assembling an authoritative symbol table
- rendering exactly one documentation artifact

Renderers do not:

- decide which artifacts exist
- perform filesystem writes
- manage multiple outputs

Those concerns belong to the backend and the compiler.

Symbol Tables
-------------

Each renderer builds **one flat, authoritative symbol table**.

Symbols are populated from multiple sources:

- project metadata
- filesystem documentation parts
- source code documentation parts
- dynamic CLI usage
- renderer-specific additions

Symbol names must be globally unique. Collisions are treated as errors.

Rendering Lifecycle
-------------------

1. A backend instantiates a renderer with a resolved ``PkitContext``.
2. The renderer loads its template.
3. Base symbols are populated automatically.
4. The renderer may add additional symbols during initialization.
5. ``render()`` produces exactly one output artifact.

Renderers do not perform file I/O directly. Rendered content is returned to
the caller and written by the compiler.
