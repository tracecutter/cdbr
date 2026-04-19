"""
pkit.cmds.sub

A sub command template with a kitchen sink of Click patterns

[[subcmd.description]]

Minimal kitchen sink demonstrating core Click patterns.

Shows:
\b
    - argument (nargs=-1)
    - boolean flag
    - dual flag (--foo/--no-foo)
    - typed option (Path)
    - value option
    - multiple=True
    - choice selection
    - counted flag (-v, -vv)
    - required option
    - renamed destination
    - context passing

[[subcmd.examples]]

Typical Workflow:

```bash
pkit sub command no luck:
    pkit sub --no-luck
```

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pbox import mark

import pkit.ui as click
from pkit.context import PkitContext
from pkit.core import sub_options

# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

HELP_DRY_RUN = "No mutations."
HELP_PATH = "O'er there."
HELP_NAME = "A rose by any other name."
HELP_LIST = "A list."
HELP_PATTERN = "Pattern like a regex or glob."
HELP_LUCK = "No, no."
HELP_MODE = "Modality"
HELP_VERBOSE = "Engage gabby gossip."
HELP_OUTPUT = "Output format."

# ---------------------------------------------------------------------------
# Command context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PkitSubContext(PkitContext):
    args: tuple[str, ...]
    dry_run: bool
    path: Path | None
    name: str | None
    list_: bool
    patterns: tuple[str, ...]
    luck: bool
    submode: str | None
    verbose: int
    output: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def sub(ctx: PkitSubContext) -> None:
    """
    Worker demonstrating simple normalization + reporting.
    """

    selected_args = ctx.args
    selected_patterns = tuple(ctx.patterns)
    selected_path = ctx.path
    selected_mode = sub_options.mode_derive(ctx)
    verbosity = ctx.verbose

    mark.info("sub invocation")

    if selected_args:
        mark.info(f"args        : {selected_args}")

    if selected_patterns:
        mark.info(f"patterns    : {selected_patterns}")

    if selected_path:
        mark.info(f"path        : {selected_path}")

    if ctx.name:
        mark.info(f"name        : {ctx.name}")

    if ctx.list_:
        mark.info("list        : enabled")

    mark.info(f"dry_run     : {ctx.dry_run}")
    mark.info(f"luck        : {ctx.luck}")
    mark.info(f"submode     : {selected_mode.name.lower()}")
    mark.info(f"verbose     : {verbosity}")
    mark.info(f"output      : {ctx.output}")

    if ctx.dry_run:
        mark.warn("dry-run enabled — no actions will be taken")

    if ctx.luck:
        mark.warn("luck flag enabled — proceeding aggressively")

    # (real work would go here)


# ---------------------------------------------------------------------------
# Click entry point
# ---------------------------------------------------------------------------


@click.command()
@click.argument("args", nargs=-1)
@click.option("-d", "--dry-run", is_flag=True, help=HELP_DRY_RUN)
@click.option("--path", type=click.Path(file_okay=False, path_type=Path), help=HELP_PATH)
@click.option("-n", "--name", help=HELP_NAME)
@click.option("-l", "--list", "list_", is_flag=True, help=HELP_LIST)
@click.option("-p", "--pattern", "patterns", multiple=True, metavar="TEXT", help=HELP_PATTERN)
@click.option("--luck/--no-luck", default=False, help=HELP_LUCK)
@click.option("--mode", "submode", type=click.Choice(["nup", "2up", "upyours"]), help=HELP_MODE)
@click.option("-v", "--verbose", count=True, help=HELP_VERBOSE)
@click.option("--output", required=True, help=HELP_OUTPUT)
@click.pass_context
def cmd(click_ctx, args, dry_run, path, name, list_, patterns, luck, submode, verbose, output):
    """
    Minimal kitchen sink demonstrating core Click patterns.
    """

    root: PkitContext = click_ctx.find_root().obj

    ctx = root.extend(
        PkitSubContext,
        args=tuple(args),
        dry_run=dry_run,
        path=path,
        name=name,
        list_=list_,
        patterns=tuple(patterns),
        luck=luck,
        submode=submode,
        verbose=verbose,
        output=output,
    )

    sub(ctx)
