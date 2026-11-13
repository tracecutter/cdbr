"""cdbr command-line entry point.

[[meta.title]]
cdbr

[[meta.tagline]]
Solve Code Break puzzles from photographs.

[[meta.brief]]
cdbr reads a photograph of a Code Break puzzle and prepares it for solving.

[[meta.author]]
John Fogelin

[[meta.copyright]]
Copyright (c) 2026 John Fogelin. All rights reserved.

[[meta.license]]
MIT. See LICENSE for details.

[[section.quickstart.intro]]
Pass a photograph of a Code Break puzzle to cdbr:

[[section.quickstart.first_command]]
```bash
cdbr puzzle.jpg
```

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved.
:license: MIT, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tempfile

import cdbr.ui as click
from npkglib import guppy, mark, signal
from npkglib.api_gen import api
from npkglib.guppy import FlatRenderer
from npkglib.mark import MarkContext

from cdbr import __version__
from cdbr.context import CdbrContext, CdbrMode
from cdbr.core import d2d
from cdbr.core.exceptions import CdbrCoreError
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.puzzle import BLOCK, CellUncertainty, PuzzleObservation, puzzle_to_toml
from cdbr.core.recognition import recognize_photo


api.discover("cdbr")
d2d.ready("cdbr")


@dataclass(frozen=True, kw_only=True)
class CdbrCmdContext(CdbrContext):
    """Resolved intent for a single puzzle-photo invocation."""

    photo: Path
    review: bool


def _review_puzzle(puzzle: PuzzleObservation, review_image: Path) -> PuzzleObservation:
    """Interactively correct uncertain cells while the temporary images exist."""

    mark.info(f"review image: {review_image}")
    click.launch(str(review_image))
    grid = [list(row) for row in puzzle.grid]
    remaining: list[CellUncertainty] = []
    uncertainties = list(puzzle.uncertainties)
    for index, item in enumerate(uncertainties):
        candidate = item.reading if item.reading.isdigit() and 1 <= int(item.reading) <= 26 else "?"
        while True:
            answer = (
                click.prompt(
                    f"Cell r{item.row:02d}c{item.column:02d} (candidate {candidate}; ?/b/q)",
                    default=candidate,
                    show_default=True,
                    err=True,
                )
                .strip()
                .lower()
            )
            if answer == "q":
                remaining.extend(uncertainties[index:])
                return replace(
                    puzzle,
                    grid=tuple(tuple(row) for row in grid),
                    uncertainties=tuple(remaining),
                )
            if answer == "?":
                remaining.append(item)
                break
            if answer == "b":
                grid[item.row - 1][item.column - 1] = BLOCK
                break
            if answer.isdigit() and 1 <= int(answer) <= 26:
                grid[item.row - 1][item.column - 1] = int(answer)
                break
            click.echo("Enter 01-26, ? to keep unresolved, b for a block, or q to finish.", err=True)
    return replace(
        puzzle,
        grid=tuple(tuple(row) for row in grid),
        uncertainties=tuple(remaining),
    )


def cdbr(ctx: CdbrCmdContext) -> None:
    """Recognize a puzzle photograph and write its TOML observation."""

    photo_format = detect_photo_format(ctx.photo)
    if photo_format is PhotoFormat.UNKNOWN:
        raise ValueError(f"Unsupported or unrecognised image format: {ctx.photo}")

    with tempfile.TemporaryDirectory(prefix="cdbr-") as directory:
        work_dir = Path(directory)
        puzzle = recognize_photo(ctx.photo, work_dir)
        if ctx.review and puzzle.uncertainties:
            puzzle = _review_puzzle(puzzle, work_dir / "review.png")
    click.echo(puzzle_to_toml(puzzle))


@click.command(
    name="cdbr",
    context_settings={
        "help_option_names": ["-h", "--help"],
        "max_content_width": 100,
        "color": True,
    },
)
@click.argument(
    "photo",
    type=click.Path(
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        path_type=Path,
    ),
)
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-error output.")
@click.option("-v", "--verbose", count=True, help="Increase diagnostic output.")
@click.option("--trace", is_flag=True, help="Enable trace instrumentation.")
@click.option("--telemetry", is_flag=True, help="Enable telemetry instrumentation.")
@click.option("--emoji/--no-emoji", default=True, help="Enable emoji prefixes in output.")
@click.option("--review", is_flag=True, help="Interactively review uncertain cells.")
@click.version_option(__version__, "-V", "--version", prog_name="cdbr")
@click.pass_context
def cdbr_main(
    click_ctx,
    photo: Path,
    quiet: bool,
    verbose: int,
    trace: bool,
    telemetry: bool,
    emoji: bool,
    review: bool,
) -> None:
    """Read a Code Break puzzle from PHOTO."""

    mark.configure(MarkContext(quiet=quiet, verbose=bool(verbose), emoji=emoji))
    signalers = tuple(name for name, enabled in (("trace", trace), ("telemetry", telemetry)) if enabled)
    signal.configure(signalers)
    if signalers:
        guppy.bootstrap()
        guppy.event_bus().sink_add(FlatRenderer())

    root = CdbrContext(mode=CdbrMode(quiet=quiet, verbose=bool(verbose), emoji=emoji))
    ctx = root.extend(CdbrCmdContext, photo=photo, review=review)
    click_ctx.obj = ctx
    cdbr(ctx)


def main() -> None:
    try:
        cdbr_main()
    except CdbrCoreError as exc:
        mark.error(str(exc))
        raise SystemExit(2) from None
    except ValueError as exc:
        mark.error(str(exc))
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        mark.error("Interrupted")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()


# Used by psym for Click usage extraction.
click_root = cdbr_main
