<!--
psym :: documentation rendered from source.
Do not edit this artifact directly.
-->
# cdbr

**Solve Code Break puzzles from photographs.**

<p align="center">
  <img src="docs/psym/assets/cdbr.png" width="180" alt="cdbr logo">
</p>

<p align="center">
<a href="https://tracecutter.github.io/cdbr/">
<img src="https://img.shields.io/badge/docs-GitHub%20Pages-blue" alt="Docs">
</a>
<img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
<img src="https://img.shields.io/badge/status-beta-lightgrey" alt="Status">
<a href="./LICENSE">
<img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</a>
</p>

---

<details>
<summary><strong>Table of Contents</strong></summary>

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Overview](#overview)
- [Solve](#solve)
- [Create](#create)
- [Web](#web)
- [Project Status](#project-status)
- [Development](#development)
- [Changelog](#changelog)
- [Links](#links)

</details>

---

## Installation

Install the command from the public Git repository into an isolated environment:

```bash
pipx install git+https://github.com/tracecutter/cdbr.git
```

Image recognition also requires ImageMagick and Tesseract to be available on
the host system. Developers should use the repository's documented editable
virtual-environment workflow.

---

## Quick start

Give cdbr a clear photograph containing the complete square puzzle and its
reference grid. It detects supported 13x13 and 15x15 boards, corrects
perspective, reads the numbered cells and supplied letters, then solves the
substitution puzzle using a British English lexicon.

### First command

```bash
cdbr puzzle.jpg
```

This prints the solved grid. Use `--orig` to print the recognised puzzle
instead, or `--image` to also write `puzzle_solved.jpg` beside the input.

### Safe exploration

cdbr never overwrites an existing solution image or puzzle file unless
`--force` is supplied. OCR uncertainty is reported rather than silently
inventing a cell value, and `--review` can be used to correct uncertain cells
before solving.

### Sample workflow

```bash
# Solve to text
cdbr puzzle.heic

# Inspect the recognised puzzle as TOML
cdbr --orig puzzle.heic

# Review uncertain cells and write on the original photograph
cdbr --review --image puzzle.heic
```

### Next steps

Use `cdbr create --help` to construct a new puzzle, or `cdbrd --help` to run
the local web application.

---

## Overview

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

---

## Solve a photograph


```text
Usage: cdbr [OPTIONS] PHOTO

  Read and solve a Code Break puzzle from PHOTO.

  PHOTO must include the complete puzzle grid and reference grid. By default
  cdbr prints the best text solution to standard output.

Options:
  -q, --quiet           Suppress non-error output.
  -v, --verbose         Enable diagnostic output.
  --trace               Enable trace instrumentation.
  --telemetry           Enable telemetry instrumentation.
  --emoji / --no-emoji  Enable emoji prefixes in output.
  --review              Interactively review uncertain cells.
  --solve               Print the text solution (the default).
  -o, --orig            Print the recognised original puzzle as TOML.
  -i, --image           Also write the solved photograph; optionally pass
                        PATH.
  -f, --force           Overwrite an existing solution image.
  -V, --version         Show the version and exit.
  --help                Show this message and exit.

  Create puzzles with 'cdbr create --help'. Run the web app with 'cdbrd
  --help'.
```


---

## Create a puzzle

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

---

## Web application

Start the local web application with:

```bash
cdbrd --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle,
scan a photograph into the playable board, or create a new puzzle. Uploaded
photographs and game sessions are currently held only for the lifetime of the
service; no database is required. Photograph recognition enters play after
human review; the lexical solver runs only when a hint or solution reveal is
requested. During play, select any numbered cell and type a letter to preview
that entry everywhere the number occurs. Enter or selecting another number
commits it, Escape cancels it, and Backspace clears a player-entered letter.
The original reference clues remain visibly distinct and cannot be changed.
Hint and solution requests show their progress over the board; an unsuccessful
search returns to the unchanged game so play can continue.

`cdbrd --reload` is intended for local development. Container deployments should
set `PORT` and run a single service process.

---

## Project status

- Python 3.11+
- British English lexical policy
- JPEG, PNG, HEIC/HEIF, AVIF, TIFF, and WebP photo input
- CLI and lightweight web application
- Experimental OCR and puzzle generation
- MIT license

OCR quality still depends on the photograph. Perspective, shadows, handwriting,
and damaged grid lines can leave cells unresolved. Puzzle generation is bounded
search: it retains the best certified candidate found during the chosen time,
although the limit can expire without producing a certified candidate.

---

## Development

Clone and install in editable mode:

```bash
git clone https://github.com/tracecutter/cdbr.git
cd cdbr
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Run the complete validation suite:

```bash
make check
pytest
```

Regenerate README, manpage, and Sphinx projections from their canonical sources:

```bash
make docs docs-sync
```

Run the web application during development:

```bash
cdbrd --reload
```

The generated `README.md`, manpages, and files under `docs/sphinx/src/` must not
be edited directly. Update structured source docstrings, `docs/psym/parts/`, or
`docs/psym/templates/`, then regenerate the projections.

System tests require ImageMagick and Tesseract. The project configuration in
`pyproject.toml` is authoritative for Python dependencies and tool settings.

---

## Changelog

### 0.1.0 — in development

- Photograph recognition with perspective correction and conservative cell OCR
- British English constraint solver with partial-result reporting
- Text, TOML, and handwriting-on-photo presentation
- Certified 15x15 puzzle generation with required and excluded words
- Lightweight web application for scanning, creating, and playing puzzles

---

## Links

- Documentation: https://tracecutter.github.io/cdbr/
- Source: https://github.com/tracecutter/cdbr
- Issues: https://github.com/tracecutter/cdbr/issues
- Author: https://github.com/tracecutter
