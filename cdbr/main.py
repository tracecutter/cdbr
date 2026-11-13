"""
cdbr.main

A single-command npkg utility template.

[[meta.title]]
cdbr

[[meta.tagline]]
A Python single-command CLI utility base project powered by npkg.

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
cdbr is a Python single-command CLI utility powered by npkg.

[[section.quickstart.install]]
```bash
pip install cdbr    # or pipx
```

[[section.quickstart.first_command]]
To start:

```bash
cdbr --help
```

[[section.status]]
- Python 3.11+
- Click-based CLI
- Single-command interface
- Proprietary license

[[section.links]]
- Docs: https://tracecutter.github.io/cdbr/
- GitHub: https://github.com/tracecutter/cdbr
- Author: https://github.com/tracecutter

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cdbr.ui as click
from npkglib import guppy, mark, signal
from npkglib.api_gen import api
from npkglib.guppy import ColumnRenderer, FlatRenderer, Sink
from npkglib.mark import MarkContext

from cdbr import __version__
from cdbr.context import CdbrContext, CdbrMode
from cdbr.core import cmd_options
from cdbr.core.exceptions import CdbrCoreError
import cdbr.core.d2d as d2d


# ---------------------------------------------------------------------------
# Core runtime initialization
# ---------------------------------------------------------------------------

api.discover("cdbr")
d2d.ready("cdbr")


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

HELP_FILE = "Project configuration file."
HELP_DIFF = "Diff output format."
HELP_DRY_RUN = "No mutations."
HELP_PATH = "O'er there."
HELP_NAME = "A rose by any other name."
HELP_LIST = "A list."
HELP_PATTERN = "Pattern like a regex or glob."
HELP_LUCK = "No, no."
HELP_MODE = "Modality."
HELP_VERBOSE = "Engage gabby gossip."
HELP_OUTPUT = "Output format."


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ArgPath = click.Path(path_type=Path)

DIFF_CANONICAL = ("2up", "lines")
DIFF_ALIASES = {
    "2up": "2up",
    "lines": "lines",
    "side-by-side": "2up",
    "side_by_side": "2up",
    "sbs": "2up",
    "1up": "lines",
    "plain": "lines",
    "classic": "lines",
}


# ---------------------------------------------------------------------------
# Command context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CdbrCmdContext(CdbrContext):
    args: tuple[str, ...]
    dry_run: bool
    path: Path | None
    name: str | None
    list_: bool
    patterns: tuple[str, ...]
    luck: bool
    cmdmode: str | None
    verbosity: int
    output: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def cdbr(ctx: CdbrCmdContext) -> None:
    """Worker demonstrating simple normalization + reporting."""

    selected_mode = cmd_options.mode_derive(ctx)

    mark.info("cdbr invocation")

    if ctx.args:
        mark.info(f"args        : {ctx.args}")

    if ctx.patterns:
        mark.info(f"patterns    : {ctx.patterns}")

    if ctx.path:
        mark.info(f"path        : {ctx.path}")

    if ctx.name:
        mark.info(f"name        : {ctx.name}")

    if ctx.list_:
        mark.info("list        : enabled")

    mark.info(f"dry_run     : {ctx.dry_run}")
    mark.info(f"luck        : {ctx.luck}")
    mark.info(f"cmdmode     : {selected_mode.name.lower()}")
    mark.info(f"verbose     : {ctx.verbosity}")
    mark.info(f"output      : {ctx.output}")

    if ctx.dry_run:
        mark.warn("dry-run enabled — no actions will be taken")

    if ctx.luck:
        mark.warn("luck flag enabled — proceeding aggressively")


# ---------------------------------------------------------------------------
# Click entry point
# ---------------------------------------------------------------------------


@click.command(
    name="cdbr",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "max_content_width": 100,
        "color": True,
    },
)
@click.argument("args", nargs=-1)
@click.option("-f", "--file", default="pyproject.toml", show_default=True, type=ArgPath, help=HELP_FILE)
@click.option("-q", "--quiet", is_flag=True, help="Suppress output.")
@click.option("--trace", is_flag=True, help="Enable trace instrumentation.")
@click.option("--telemetry", is_flag=True, help="Enable telemetry instrumentation.")
@click.option("--layout", type=click.Choice(["1up", "nup"]), default="1up", show_default=True, help="Output layout.")
@click.option("--emoji/--no-emoji", default=True, help="Enable emoji prefixes in output. [default: true]")
@click.option("--diff", callback=_diff_pick, metavar="{2up|lines}", default="2up", show_default=True, help=HELP_DIFF)
@click.option("-d", "--dry-run", is_flag=True, help=HELP_DRY_RUN)
@click.option("--path", type=click.Path(file_okay=False, path_type=Path), help=HELP_PATH)
@click.option("-n", "--name", help=HELP_NAME)
@click.option("-l", "--list", "list_", is_flag=True, help=HELP_LIST)
@click.option("-p", "--pattern", "patterns", multiple=True, metavar="TEXT", help=HELP_PATTERN)
@click.option("--luck/--no-luck", default=False, help=HELP_LUCK)
@click.option("--mode", "cmdmode", type=click.Choice(["nup", "2up", "upyours"]), help=HELP_MODE)
@click.option("-v", "--verbose", count=True, help=HELP_VERBOSE)
@click.option("--output", required=True, help=HELP_OUTPUT)
@click.version_option(__version__, "-V", "--version", prog_name="cdbr")
@click.pass_context
def cdbr_main(
    click_ctx,
    args,
    file,
    quiet,
    trace,
    telemetry,
    layout,
    emoji,
    diff,
    dry_run,
    path,
    name,
    list_,
    patterns,
    luck,
    cmdmode,
    verbose,
    output,
):
    """
    Minimal single-command kitchen sink demonstrating core Click patterns.

    See `man cdbr` or the user guide for full documentation.
    """

    mark.configure(MarkContext(quiet=quiet, verbose=bool(verbose), emoji=emoji))

    signalers = tuple(
        name
        for name, enabled in (
            ("trace", trace),
            ("telemetry", telemetry),
        )
        if enabled
    )
    signal.configure(signalers)

    if signalers or layout != "1up":
        guppy.bootstrap()
        guppy.event_bus().sink_add(_make_renderer(layout))

    try:
        diff_mode = DIFF_ALIASES[diff.lower()]
    except KeyError:
        raise click.UsageError(f"Invalid diff mode: {diff}") from None

    mode = CdbrMode(quiet=quiet, verbose=bool(verbose), emoji=emoji, diff=diff_mode)
    root = CdbrContext(mode=mode)

    ctx = root.extend(
        CdbrCmdContext,
        args=tuple(args),
        dry_run=dry_run,
        path=path,
        name=name,
        list_=list_,
        patterns=tuple(patterns),
        luck=luck,
        cmdmode=cmdmode,
        verbosity=verbose,
        output=output,
    )

    click_ctx.obj = ctx

    cdbr(ctx)


# ---------------------------------------------------------------------------
# Process entry point
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        cdbr_main()

    except CdbrCoreError as e:
        mark.error(str(e))
        raise SystemExit(2) from None

    except ValueError as e:
        mark.error(str(e))
        raise SystemExit(2) from None

    except KeyboardInterrupt:
        mark.error("Interrupted")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()


# Used by psym for Click usage extraction.
click_root = cdbr_main
