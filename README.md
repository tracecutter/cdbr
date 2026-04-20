<!--
psym :: documentation rendered from source.
Do not edit this artifact directly.
-->
# pkit

**A Python project CLI utility base project powered by npkg.**

<p align="center">
  <img src="docs/pkit/assets/pkit.png" width="180" alt="pkit logo">
</p>

<p align="center">
<a href="https://tracecutter.github.io/pkit/">
<img src="https://img.shields.io/badge/docs-GitHub%20Pages-blue" alt="Docs">
</a>
<img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
<img src="https://img.shields.io/badge/status-experimental-lightgrey" alt="Status">
<a href="./LICENSE">
<img src="https://img.shields.io/badge/license-proprietary-lightgrey" alt="License">
</a>
</p>

---

<details>
<summary><strong>Table of Contents</strong></summary>

- [Installation](#installation)
- [D2D](#d2d)
- [Quick Start](#quick-start)
- [Overview](#overview)
- [Usage](#usage)
- [Renderer Usage](#renderer-usage)
- [Project Status](#project-status)
- [Development](#development)
- [Changelog](#changelog)
- [Links](#links)

</details>

---

## Installation 

```bash
pip install pkit    # or pipx
```

---

## Asset delivery (d2d) 


Some applications bundle non-Python artifacts such as command wrappers,
man pages, examples, or templates. These artifacts are delivered to user
directories using the **Distribution-to-Destination (d2d)** mechanism.

Artifacts bundled inside a package are stored under:

    <package>/_assets/

and routed into user directories according to a personal policy defined in:

    ~/.config/d2d/routes.toml

Example configuration:

```toml
[routes]
bin = "~/.local/bin"
man = "~/.local/share/man"
```

On first run, the application will explain how to create this configuration
file if it does not already exist.

Once configured, artifact delivery happens automatically and silently.

---

## Quick start 

pkit is a Python CLI utiity powered by npkg.

### First command

To start:

```bash
pkit --help
```

### Safe exploration

Most pkit commands support --dry-run, which shows what would change without modifying your project.
When exploring, it’s a good idea to start with --dry-run until you’re comfortable with the results.

### Sample workflow

A typical workflow might look like this:

```bash
pkit sub
pkit help
```

### Next steps

See the User Guide for more detailed workflows.

---

## Overview 

For the full user guide, design notes, and rationale, see:

https://tracecutter.github.io/npkg/

Built with Sphinx and hosted on GitHub Pages.

---

## Usage 


```text
Usage:  [OPTIONS] COMMAND [ARGS]...

  This package is forked by pfork to bootstrap a new npkg powered package.

  Run `pkit <command> --help` for command-specific help.

  See `man pkit` or the user guide for full documentation.

  Full documentation: https://tracecutter.github.io/pkit/

Options:
  -f, --file PATH       Project configuration file.  [default: pyproject.toml]
  -q, --quiet           Suppress output.
  -v, --verbose         Verbose output.
  --trace               Enable trace instrumentation.
  --telemetry           Enable telemetry instrumentation.
  --layout [1up|nup]    Output layout.  [default: 1up]
  --emoji / --no-emoji  Enable emoji prefixes in output. [default: true]
  --diff {2up|lines}    Diff output format.  [default: 2up]
  -V, --version         Show the version and exit.
  --help                Show this message and exit.

Commands:
  help  Display help for pkit or a named subcommand.
  sub   Minimal kitchen sink demonstrating core Click patterns.
```


### Writing custom documentation renderers 

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

---

## Project status 

- Python 3.11+
- Click-based CLI
- Proprietary license

---

## Development 

Clone and install in editable mode:

```bash
git clone https://github.com/tracecutter/pkit.git
cd pkit
make install
```

To build docs locally:

```bash
make docs
```

Run checks:

```bash
make check
```

Run tests:

```bash
pytest
```

Update README usage:

```bash
make readme
```

---

## Changelog 

### v1.0.0
- Initial public release
- Dependency inspection and mutation
- README usage auto-generation
- Designed as a reference implementation for `npkg`

---

## Links 

- Docs: https://tracecutter.github.io/pkit/
- GitHub: https://github.com/tracecutter/pkit
- Author: https://github.com/tracecutter
