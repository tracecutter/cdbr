User Guide
==========

Using pfig effectively.

The core functional blocks of pfig are dependency management, pyproject.toml hygene, and documentation generation.

``pfig`` is intentionally conservative.

- ``pyproject.toml`` is the source of truth
- Source code is the preferred source of documentation.
- No silent upgrades
- No implicit dependency resolution
- No rewriting intent without consent

Commands fall into two clear categories:

- **Inspectors** — read and report project intent
- **Mutators** — make explicit, diffable changes (with dry-run support)

This makes ``pfig`` safe for:

- interactive use
- CI pipelines
- automated project scaffolding (e.g. via ``npkg``)

For the full user guide, design notes, and rationale, see:

https://tracecutter.github.io/pfig/

Built with Sphinx and hosted on GitHub Pages.

Status
------

- Python 3.11+
- Click-based CLI
- Proprietary license

Links
-----

- Docs: https://tracecutter.github.io/pfig/
- GitHub: https://github.com/tracecutter/pfig
- Author: https://github.com/tracecutter
