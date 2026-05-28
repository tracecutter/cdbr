"""
pkit.main

A npkg utility.

[[meta.title]]
pkit

[[meta.tagline]]
A Python project CLI utility base project powered by npkg.

[[meta.brief]]
This package is forked by pfork to bootstrap a new npkg powered package.

[[meta.author]]
John Fogelin

[[meta.copyright]]
Copyright (c) 2026 John Fogelin. All rights reserved.

[[meta.license]]
PROPRIETARY. See LICENSE for details.

[[section.overview]]
For the full user guide, design notes, and rationale, see:

https://tracecutter.github.io/npkg/

Built with Sphinx and hosted on GitHub Pages.

[[section.quickstart.intro]]
pkit is a Python CLI utiity powered by npkg.

[[section.quickstart.install]]
```bash
pip install pkit    # or pipx
```

[[section.quickstart.safety]]
Most pkit commands support --dry-run, which shows what would change without modifying your project.
When exploring, it’s a good idea to start with --dry-run until you’re comfortable with the results.

[[section.quickstart.first_command]]
To start:

```bash
pkit --help
```

[[section.quickstart.workflow]]
A typical workflow might look like this:

```bash
pkit sub
pkit help
```

[[section.quickstart.next]]
See the User Guide for more detailed workflows.

[[section.status]]
- Python 3.11+
- Click-based CLI
- Proprietary license

[[section.links]]
- Docs: https://tracecutter.github.io/pkit/
- GitHub: https://github.com/tracecutter/pkit
- Author: https://github.com/tracecutter

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""

import pkit.ui as click
from pathlib import Path
from npkglib import mark, signal, guppy
from npkglib.mark import MarkContext
from npkglib.guppy import Sink, FlatRenderer, ColumnRenderer

from pkit.cmds import discover
from pkit import __version__
from pkit.context import PkitContext, PkitMode
from pkit.core.exceptions import PkitCoreError
import pkit.core.d2d as d2d
from pkit.api import api

# ---------------------------------------------------------------------------
# Core runtime initialization
# ---------------------------------------------------------------------------

# Populate API registry by importing package modules.
# In pkit, API declaration via @api is a core feature.
api.discover("pkit")

# Initialize d2d asset routing (manpages, examples, etc.).
d2d.ready("pkit")

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

ArgPath = click.Path(path_type=Path)

SYSTEM_COMMANDS = {"help"}

HELP_FILE = "Project configuration file."
HELP_DIFF = "Diff output format."
HELP_SIGNAL = "Enable signalling (e.g. trace,telemetry), comma-separated selection."

DIFF_CANONICAL = ("2up", "lines")
DIFF_ALIASES = {
    # canonical
    "2up": "2up",
    "lines": "lines",
    # side-by-side aliases
    "side-by-side": "2up",
    "side_by_side": "2up",
    "sbs": "2up",
    # line-based aliases
    "1up": "lines",
    "plain": "lines",
    "classic": "lines",
}


def _diff_pick(ctx, param, value):
    if value is None:
        return "2up"

    key = value.lower()
    try:
        return DIFF_ALIASES[key]
    except KeyError:
        raise click.BadParameter(
            f"Invalid diff format '{value}'. " f"Choose from {', '.join(DIFF_CANONICAL)}."
        ) from None


def _make_renderer(layout: str) -> Sink:
    if layout == "nup":
        return ColumnRenderer()
    return FlatRenderer()


# ------------------------------------------------------------------
# Click Main Function: The entry point you are looking for
# ------------------------------------------------------------------


@click.group(
    name="pkit",
    invoke_without_command=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
        "max_content_width": 100,
        "color": True,
    },
)
@click.option("-f", "--file", "file", default="pyproject.toml", show_default=True, type=ArgPath, help=HELP_FILE)
@click.option("-q", "--quiet", is_flag=True, help="Suppress output.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.option("--trace", is_flag=True, help="Enable trace instrumentation.")
@click.option("--telemetry", is_flag=True, help="Enable telemetry instrumentation.")
@click.option("--layout", type=click.Choice(["1up", "nup"]), default="1up", show_default=True, help="Output layout.")
@click.option("--emoji/--no-emoji", default=True, help="Enable emoji prefixes in output. [default: true]")
@click.option("--diff", callback=_diff_pick, metavar="{2up|lines}", default="2up", show_default=True, help=HELP_DIFF)
@click.version_option(__version__, "-V", "--version", prog_name="pkit")
@click.pass_context
def pkit_main(click_ctx, *, file, quiet, verbose, emoji, diff, trace, telemetry, layout):
    """
    This package is forked by pfork to bootstrap a new npkg powered package.

    Run `pkit <command> --help` for command-specific help.

    See `man pkit` or the user guide for full documentation.

    Full documentation: https://tracecutter.github.io/pkit/
    """

    # Configure narration policy
    mark.configure(MarkContext(quiet=quiet, verbose=verbose, emoji=emoji))

    # Signal configuration
    signalers = tuple(name for name, enabled in (("trace", trace), ("telemetry", telemetry)) if enabled)
    signal.configure(tuple(signalers))

    # Guppy bootstrap
    if signalers or layout != "1up":
        guppy.bootstrap()
        guppy.event_bus().sink_add(_make_renderer(layout))

    # No subcommand → show help
    if click_ctx.invoked_subcommand is None:
        click.echo(pkit_main.get_help(click_ctx))
        click_ctx.exit(0)

    # bail out before context constructed for SYSTEM_COMMANDS
    if click_ctx.invoked_subcommand in SYSTEM_COMMANDS:
        return

    # Normalize CLI options
    try:
        diff_mode = DIFF_ALIASES[diff.lower()]
    except KeyError:
        raise click.UsageError(f"Invalid diff mode: {diff}") from None

    # Build context with selected mode
    mode = PkitMode(quiet=quiet, verbose=verbose, emoji=emoji, diff=diff_mode)
    pkit_ctx = PkitContext(mode=mode)

    # Attach pkit context to Click root
    click_ctx.obj = pkit_ctx


# The main function that happens before pkit_main.
def main() -> None:
    try:
        # ---- register commands
        for name, command in discover().items():
            pkit_main.add_command(command, name=name)

        # ---- invoke CLI
        pkit_main()

    except PkitCoreError as e:
        mark.error(str(e))
        raise SystemExit(2) from None

    except ValueError as e:  # For now... we need better exception raising
        mark.error(str(e))
        raise SystemExit(2) from None

    except KeyboardInterrupt:
        mark.error("Interrupted")
        raise SystemExit(130) from None


# The entry point
if __name__ == "__main__":
    main()


def _wire_click_root():
    """
    Ensure the root Click command has all discovered subcommands attached.
    Safe to call multiple times.
    """
    if not pkit_main.commands:
        for name, command in discover().items():
            pkit_main.add_command(command, name=name)
    return pkit_main


click_root = _wire_click_root()  # Used by psym for Click usage extraction
