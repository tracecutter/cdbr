"""cdbr command-line entry point.

[[meta.title]]
cdbr

[[meta.tagline]]
Solve Code Break puzzles from photographs.

[[meta.brief]]
cdbr reads, solves, and creates numbered Code Break puzzles.

[[meta.author]]
John Fogelin

[[meta.copyright]]
Copyright (c) 2026 John Fogelin. All rights reserved.

[[meta.license]]
MIT. See LICENSE for details.

[[section.quickstart.intro]]
Give cdbr a clear photograph containing the complete 15x15 puzzle and its
reference grid. It corrects perspective, reads the numbered cells and supplied
letters, then solves the substitution puzzle using a British English lexicon.

[[section.quickstart.install]]
Install the command from the public Git repository into an isolated environment:

```bash
pipx install git+https://github.com/tracecutter/cdbr.git
```

Image recognition also requires ImageMagick and Tesseract to be available on
the host system. Developers should use the repository's documented editable
virtual-environment workflow.

[[section.quickstart.first_command]]
```bash
cdbr puzzle.jpg
```

This prints the solved grid. Use `--orig` to print the recognised puzzle
instead, or `--image` to also write `puzzle_solved.jpg` beside the input.

[[section.quickstart.safety]]
cdbr never overwrites an existing solution image or puzzle file unless
`--force` is supplied. OCR uncertainty is reported rather than silently
inventing a cell value, and `--review` can be used to correct uncertain cells
before solving.

[[section.quickstart.workflow]]
```bash
# Solve to text
cdbr puzzle.heic

# Inspect the recognised puzzle as TOML
cdbr --orig puzzle.heic

# Review uncertain cells and write on the original photograph
cdbr --review --image puzzle.heic
```

[[section.quickstart.next]]
Use `cdbr create --help` to construct a new puzzle, or `cdbrd --help` to run
the local web application.

[[section.overview]]
Code Break (also called Codeword) puzzles replace every letter in a crossword-like
grid with a number from 1 to 26. Equal numbers represent equal letters, different
numbers represent different letters, and a small reference grid supplies the
starting clues.

cdbr supports four related workflows:

- recognise and solve a photographed puzzle;
- preserve the recognised board as deterministic TOML for review or testing;
- render the solution in handwriting on the source photograph; and
- construct and independently certify new 15x15 puzzles.

The companion `cdbrd` executable serves the same solving and generation engine
through a lightweight local web application. CLI solving does not require the
web service to be running.

OCR, lexical solving, puzzle construction, and presentation are separate stages.
A complete solution is reported as unique only when the configured search is
exhausted and exactly one solution remains under the active lexicon.

[[section.create]]
Puzzle construction is available through the existing secondary mode:

```bash
cdbr create --include PERFECT --include PETERSFIELD \
    --clues 3 --output puzzle.toml --image puzzle.png
```

`--include WORD` requires a themed answer word and may be repeated.
`--exclude WORD` prevents unwanted filler. The generator fills a 15x15 topology,
selects the requested number of reference clues, and independently certifies the
result with the solver.

Use `--best-of MINUTES` with `--output` to keep searching and replace the output
only when a certified candidate has fewer black cells. `--keep-candidates DIR`
archives every certified candidate for later editorial review. Generation can be
computationally expensive; reproducible searches should specify `--seed`.

Run `cdbr create --help` for the complete set of construction limits.

[[section.web]]
Start the local web application with:

```bash
cdbrd --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle,
scan a photograph into the playable board, or create a new puzzle. Uploaded
photographs and game sessions are currently held only for the lifetime of the
service; no database is required.

`cdbrd --reload` is intended for local development. Container deployments should
set `PORT` and run a single service process.

[[section.status]]
- Python 3.11+
- British English lexical policy
- JPEG, PNG, HEIC/HEIF, AVIF, TIFF, and WebP photo input
- CLI and lightweight web application
- Experimental OCR and puzzle generation
- MIT license

OCR quality still depends on the photograph. Perspective, shadows, handwriting,
and damaged grid lines can leave cells unresolved. Puzzle generation is bounded
search: a time limit can expire without producing a certified candidate.

[[section.links]]
- Documentation: https://tracecutter.github.io/cdbr/
- Source: https://github.com/tracecutter/cdbr
- Issues: https://github.com/tracecutter/cdbr/issues
- Author: https://github.com/tracecutter

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved.
:license: MIT, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys
import tempfile
import time

import cdbr.ui as click
from npkglib import guppy, mark, signal
from npkglib.api_gen import api
from npkglib.guppy import FlatRenderer
from npkglib.mark import MarkContext

from cdbr import __version__
from cdbr.context import CdbrContext, CdbrMode
from cdbr.core import d2d
from cdbr.core.exceptions import CdbrCoreError
from cdbr.core.generator import GenerationLimits, generate_puzzle, generated_puzzle_to_toml
from cdbr.core.lexicon import english_lexicon
from cdbr.core.model import CodewordPuzzle
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.presentation import solution_rows, write_generated_puzzle_image, write_solution_photo
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
    epilog="Create puzzles with 'cdbr create --help'. Run the web app with 'cdbrd --help'.",
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
@click.option("-v", "--verbose", is_flag=True, help="Enable diagnostic output.")
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
    verbose: bool,
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
    """Read and solve a Code Break puzzle from PHOTO.

    PHOTO must include the complete puzzle grid and reference grid. By default
    cdbr prints the best text solution to standard output.
    """

    mark.configure(MarkContext(quiet=quiet, verbose=verbose, emoji=emoji))
    signalers = tuple(name for name, enabled in (("trace", trace), ("telemetry", telemetry)) if enabled)
    signal.configure(signalers)
    if signalers:
        guppy.bootstrap()
        guppy.event_bus().sink_add(FlatRenderer())

    if solve and orig:
        raise click.UsageError("--solve and --orig are mutually exclusive")
    destination = _solution_destination(photo, image, solution_image, force)

    root = CdbrContext(mode=CdbrMode(quiet=quiet, verbose=verbose, emoji=emoji))
    ctx = root.extend(
        CdbrCmdContext,
        photo=photo,
        review=review,
        orig=orig,
        solution_image=destination,
    )
    click_ctx.obj = ctx
    cdbr(ctx)


@click.command(name="create", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--seed", type=int, default=0, show_default=True, help="Make generation reproducible.")
@click.option(
    "--attempts",
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Maximum topology and fill attempts for each seed.",
)
@click.option(
    "--best-of",
    type=click.FloatRange(min=0),
    default=0.0,
    show_default=True,
    metavar="MINUTES",
    help="Search for MINUTES and retain the certified puzzle with fewest black cells.",
)
@click.option(
    "--max-candidates",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Stop best-of search after this many certified candidates; zero means unlimited.",
)
@click.option(
    "--seconds",
    type=click.FloatRange(min=0),
    default=600.0,
    show_default=True,
    help="Hard wall-clock limit; zero means unlimited.",
)
@click.option(
    "--slots",
    type=click.IntRange(min=1, max=60),
    default=28,
    show_default=True,
    help="Target number of across and down answer slots.",
)
@click.option(
    "--min-word-length",
    type=click.IntRange(min=2, max=15),
    default=4,
    show_default=True,
    help="Shortest generated filler word.",
)
@click.option(
    "--max-word-length",
    type=click.IntRange(min=2, max=15),
    default=14,
    show_default=True,
    help="Longest generated filler word.",
)
@click.option(
    "--include", "included_words", multiple=True, help="Require WORD in the completed puzzle.", metavar="WORD"
)
@click.option("--exclude", "excluded_words", multiple=True, help="Forbid WORD as generated filler.", metavar="WORD")
@click.option(
    "--min-score", type=click.FloatRange(min=0), default=3.5, show_default=True, help="Minimum word-frequency score."
)
@click.option(
    "--fill-nodes",
    type=click.IntRange(min=1),
    default=500,
    show_default=True,
    help="Maximum search nodes used to fill one candidate.",
)
@click.option(
    "--certify-nodes",
    type=click.IntRange(min=1),
    default=50_000,
    show_default=True,
    help="Maximum solver nodes used to certify uniqueness.",
)
@click.option(
    "--clues",
    type=click.IntRange(min=0, max=26),
    default=3,
    show_default=True,
    help="Exact number of supplied reference letters.",
)
@click.option("--answer", is_flag=True, help="Include the answer grid in the TOML output.")
@click.option(
    "--image", "puzzle_image", type=click.Path(dir_okay=False, path_type=Path), help="Write a printable puzzle image."
)
@click.option(
    "--skew",
    type=click.FloatRange(min=-5, max=5),
    default=0.0,
    show_default=True,
    help="Rotate the rendered page slightly.",
)
@click.option(
    "-o", "--output", type=click.Path(dir_okay=False, path_type=Path), help="Write TOML to PATH instead of stdout."
)
@click.option(
    "--keep-candidates",
    type=click.Path(file_okay=False, path_type=Path),
    metavar="DIRECTORY",
    help="Archive every certified candidate as TOML and PNG.",
)
@click.option("-f", "--force", is_flag=True, help="Overwrite an existing output file.")
def create_main(
    seed: int,
    attempts: int,
    best_of: float,
    max_candidates: int,
    seconds: float,
    slots: int,
    min_word_length: int,
    max_word_length: int,
    included_words: tuple[str, ...],
    excluded_words: tuple[str, ...],
    min_score: float,
    fill_nodes: int,
    certify_nodes: int,
    clues: int,
    answer: bool,
    puzzle_image: Path | None,
    skew: float,
    output: Path | None,
    keep_candidates: Path | None,
    force: bool,
) -> None:
    """Construct and independently certify a 15x15 Codeword puzzle.

    Repeat --include to place themed words and --exclude to reject unwanted
    filler. Generation is bounded search and may finish without a candidate.
    """

    if output is not None and output.exists() and not force:
        raise click.UsageError(f"Output already exists: {output} (use --force to overwrite)")
    if puzzle_image is not None and puzzle_image.exists() and not force:
        raise click.UsageError(f"Puzzle image already exists: {puzzle_image} (use --force to overwrite)")
    if best_of and output is None:
        raise click.UsageError("--best-of requires --output so improvements can be saved safely")
    limits = GenerationLimits(
        target_slots=slots,
        minimum_word_length=min_word_length,
        max_word_length=max_word_length,
        minimum_score=min_score,
        fill_nodes=fill_nodes,
        certify_nodes=certify_nodes,
        clue_count=clues,
        attempts=attempts,
        seconds=seconds,
    )
    lexicon = english_lexicon()

    def archive(generated) -> None:
        if keep_candidates is None:
            return
        keep_candidates.mkdir(parents=True, exist_ok=True)
        blocks = sum(symbol is None for row in generated.puzzle.grid for symbol in row)
        stem = (
            f"candidate-seed-{generated.seed:06d}-b{blocks:03d}"
            f"-c{len(generated.puzzle.clues):02d}-n{generated.certification.nodes:06d}"
        )
        candidate_toml = keep_candidates / f"{stem}.toml"
        candidate_png = keep_candidates / f"{stem}.png"
        candidate_toml.write_text(
            generated_puzzle_to_toml(generated, include_answer=True),
            encoding="utf-8",
        )
        write_generated_puzzle_image(
            candidate_png,
            generated.puzzle,
            seed=generated.seed,
            skew_degrees=skew,
        )
        mark.info(f"candidate: {candidate_toml}")

    def save(generated) -> None:
        text = generated_puzzle_to_toml(generated, include_answer=answer)
        if output is None:
            click.echo(text)
        else:
            output.write_text(text, encoding="utf-8")
            mark.info(f"puzzle: {output}")
        if puzzle_image is not None:
            write_generated_puzzle_image(
                puzzle_image,
                generated.puzzle,
                seed=generated.seed,
                skew_degrees=skew,
            )
            mark.info(f"puzzle image: {puzzle_image}")

    if not best_of:
        generated = generate_puzzle(
            lexicon,
            seed=seed,
            limits=limits,
            progress=lambda message: click.echo(message, err=True),
            required_words=included_words,
            excluded_words=excluded_words,
        )
        archive(generated)
        save(generated)
        return

    deadline = time.monotonic() + best_of * 60
    best = None
    best_quality: tuple[int, int, int] | None = None
    candidate_seed = seed
    candidates = 0
    while time.monotonic() < deadline and (not max_candidates or candidates < max_candidates):
        remaining = deadline - time.monotonic()
        candidate_limits = replace(
            limits,
            seconds=min(60.0, remaining),
            attempts=min(limits.attempts, 20),
        )

        def report_progress(message: str, active_seed: int = candidate_seed) -> None:
            click.echo(f"seed {active_seed}: {message}", err=True)

        try:
            candidate = generate_puzzle(
                lexicon,
                seed=candidate_seed,
                limits=candidate_limits,
                progress=report_progress,
                required_words=included_words,
                excluded_words=excluded_words,
            )
        except ValueError:
            candidate_seed += 1
            continue
        candidates += 1
        blocks = sum(symbol is None for row in candidate.puzzle.grid for symbol in row)
        archive(candidate)
        quality = (blocks, len(candidate.puzzle.clues), candidate.certification.nodes)
        if best_quality is None or quality < best_quality:
            best = candidate
            best_quality = quality
            save(candidate)
            mark.info(
                f"new best: {blocks} black cells, {len(candidate.puzzle.clues)} clues "
                f"(seed {candidate.seed}; {candidates} certified candidates)"
            )
        candidate_seed += 1
    if best is None:
        raise ValueError("No certified puzzle found within the best-of budget")
    assert best_quality is not None
    mark.info(f"best-of complete: {best_quality[0]} black cells after {candidates} certified candidates")


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "create":
            create_main.main(args=sys.argv[2:], prog_name="cdbr create")
        else:
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
