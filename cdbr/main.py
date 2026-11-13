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

This prints the solved grid. Use ``--orig`` to print the recognised puzzle
instead, or ``--image`` to also write ``puzzle_solved.jpg`` beside the input.

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
from cdbr.core.lexicon import english_lexicon
from cdbr.core.model import CodewordPuzzle
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.presentation import solution_rows, write_solution_photo
from cdbr.core.puzzle import BLOCK, CellUncertainty, PuzzleObservation, puzzle_to_toml
from cdbr.core.recognition import recognize_photo
from cdbr.core.solver import solve


api.discover("cdbr")
d2d.ready("cdbr")


@dataclass(frozen=True, kw_only=True)
class CdbrCmdContext(CdbrContext):
    """Resolved intent for a single puzzle-photo invocation."""

    photo: Path
    review: bool
    orig: bool
    solution_image: Path | None


class OptionalImageCommand(click.Command):
    """Allow ``--image[=PATH]`` while retaining PHOTO as a positional argument."""

    def parse_args(self, ctx, args: list[str]) -> list[str]:
        operands = sum(1 for argument in args if not argument.startswith("-"))
        rewritten: list[str] = []
        index = 0
        while index < len(args):
            argument = args[index]
            attached: str | None = None
            if argument.startswith("--image="):
                attached = argument.partition("=")[2]
            elif argument.startswith("-i") and argument != "-i":
                attached = argument[2:]
            if attached is not None:
                rewritten.extend(("--solution-image", attached))
            elif argument in {"-i", "--image"} and operands >= 2 and index + 1 < len(args):
                rewritten.extend(("--solution-image", args[index + 1]))
                operands -= 1
                index += 1
            else:
                rewritten.append(argument)
            index += 1
        return super().parse_args(ctx, rewritten)


def _solution_destination(photo: Path, requested: bool, explicit: Path | None, force: bool) -> Path | None:
    if not requested and explicit is None:
        return None
    destination = explicit or photo.with_name(f"{photo.stem}_solved{photo.suffix}")
    if destination.resolve() == photo.resolve():
        raise ValueError("Solution image must not overwrite the source photograph")
    if destination.exists() and not force:
        raise ValueError(f"Solution image already exists: {destination} (use --force to overwrite)")
    return destination


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
        if not ctx.orig or ctx.solution_image is not None:
            codeword = CodewordPuzzle.from_observation(puzzle)
            result = solve(codeword, english_lexicon())
            if result.solutions:
                mapping = result.solutions[0].mapping
                if len(result.solutions) > 1:
                    mark.warn("Multiple solutions found; showing the first")
                elif not result.exhausted:
                    mark.warn("Search stopped early; solution is provisional")
            else:
                mapping = result.best_mapping
                mark.warn("Puzzle could not be solved under the active lexicon; showing the best partial attempt")
            if ctx.solution_image is not None:
                write_solution_photo(
                    ctx.photo,
                    ctx.solution_image,
                    codeword,
                    mapping,
                    work_dir,
                )
                mark.info(f"solution image: {ctx.solution_image}")
            if not ctx.orig:
                click.echo("\n".join(solution_rows(codeword, mapping)))
        if ctx.orig:
            click.echo(puzzle_to_toml(puzzle))


@click.command(
    name="cdbr",
    cls=OptionalImageCommand,
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
@click.option("--solve", is_flag=True, help="Print the text solution (the default).")
@click.option("-o", "--orig", is_flag=True, help="Print the recognised original puzzle as TOML.")
@click.option("-i", "--image", is_flag=True, help="Also write the solved photograph; optionally pass PATH.")
@click.option(
    "--solution-image",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    hidden=True,
)
@click.option("-f", "--force", is_flag=True, help="Overwrite an existing solution image.")
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
    solve: bool,
    orig: bool,
    image: bool,
    solution_image: Path | None,
    force: bool,
) -> None:
    """Read a Code Break puzzle from PHOTO."""

    mark.configure(MarkContext(quiet=quiet, verbose=bool(verbose), emoji=emoji))
    signalers = tuple(name for name, enabled in (("trace", trace), ("telemetry", telemetry)) if enabled)
    signal.configure(signalers)
    if signalers:
        guppy.bootstrap()
        guppy.event_bus().sink_add(FlatRenderer())

    if solve and orig:
        raise click.UsageError("--solve and --orig are mutually exclusive")
    destination = _solution_destination(photo, image, solution_image, force)

    root = CdbrContext(mode=CdbrMode(quiet=quiet, verbose=bool(verbose), emoji=emoji))
    ctx = root.extend(
        CdbrCmdContext,
        photo=photo,
        review=review,
        orig=orig,
        solution_image=destination,
    )
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
