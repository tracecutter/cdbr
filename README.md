<!--
psym :: documentation rendered from source.
Do not edit this artifact directly.
-->
# cdbr

**Solve Code Break puzzles from photographs.**

**Play at [codebreak.foghub.com](https://codebreak.foghub.com).**
Open a puzzle from the collection, scan one from your book, or create your own.
The hosted app runs in your browser and needs no installation or account.

<p align="center">
  <a href="https://codebreak.foghub.com"><img src="docs/psym/assets/gameplay.png" width="900" alt="Puzzle 78 with its printed starting letters on both the board and reference grid"></a>
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

- [Local Installation](#local-installation)
- [Command Line Quick Start](#command-line-quick-start)
- [Overview](#overview)
- [Solve A Photograph](#solve-a-photograph)
- [Create A Puzzle](#create-a-puzzle)
- [Run The Web App Locally](#run-the-web-app-locally)
- [Project Status](#project-status)
- [Development](#development)
- [Changelog](#changelog)
- [Links](#links)

</details>

---

## Local installation

Install the command from the public Git repository into an isolated environment:

```bash
pipx install git+https://github.com/tracecutter/cdbr.git
```

Image recognition also requires ImageMagick and Tesseract to be available on
the host system. Developers should use the repository's documented editable
virtual-environment workflow.

---

## Command-line quick start

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

## Run the web app locally

Start the local web application with:

```bash
cdbrd --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/. The web interface can play a corpus puzzle,
scan a photograph into the playable board, or create a new puzzle. Uploaded
photographs and game sessions are currently held only for the lifetime of the
service; no database is required. A successful scan opens a board review.
Accepting the scan checks for a complete solution before play, with the option
to review again or play anyway if the search cannot finish. During play, select
any numbered cell and type a letter to preview that entry everywhere the number
occurs. Enter or selecting another number
commits it, Escape cancels it, and Backspace clears a player-entered letter.
The letter rails above and below the board cross out letters already assigned,
with a compact vowel rail repeating the same state. The one-to-one code prevents
a letter being entered for two numbers. The original reference clues remain
visibly distinct and cannot be changed. Check highlights incorrect player entries
throughout both the puzzle and reference grid without revealing replacements.
On a narrow screen the puzzle, 2x13 reference grid, and an on-screen QWERTY
keyboard form one compact play surface. Two-finger pinch gestures enlarge only
the puzzle board, which can then be panned without losing the reference grid.
In Play, choose a named puzzle from either collection or use **Pick one** to
open a random board. Packaged puzzles start with their printed clues. Click the
same reference cell twice to put a hint directly on both grids when a letter is
available. Hint and reveal requests can search from checked player entries, and
show progress over the board. A tentative hint carries a warning in the game
panel.

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

`make check` validates system dependencies, generated documentation, Ruff,
Black, mypy, and version lineage. `make test` is the equivalent short form for
the default pytest run. Use `make help` to list the complete inherited npkg
target set.

Preview the web application directly from the active development environment:

```bash
make preview
```

This starts the configured `cdbrd` service at http://127.0.0.1:8000/ without
building or running a container. It remains in the foreground until interrupted.

Run the OCR corpus benchmark, optionally limiting an experiment to a single
puzzle. Benchmark targets always start again from the source photograph; cached
recognition is for explicit debugging commands, never benchmark evidence:

```bash
make benchmark
make benchmark BENCHMARK_ARGS="--puzzle 48"
make benchmark-audit
make benchmark-audit BENCHMARK_ARGS="--manifest corpus/telegraph.toml --audit-dir build/telegraph-audit --summary-output build/telegraph-audit/summary.json"
```

`make benchmark-audit` reruns OCR and independent search, then regenerates the
error-first number, reference-clue, publisher-validation, and search-outcome
pages beneath `build/corpus-audit/`. Corpus benchmarks are engineering tools and
are intentionally outside the quick `make check` gate. The same directory
retains `summary.json` for before-and-after comparisons. Add
`BENCHMARK_ARGS="--no-solve"` when collecting OCR review data alone. Use
`--solve-timeout` to change the default 120-second budget per puzzle in each
search lane. The terminal reports progress through those lanes.

The default benchmark calls the same recogniser as the web scanner. For a
geometry diagnosis, call `recognize_photo(photo, work_dir, geometry_debug=True)`
to save the corner warp, padding, traced vertex mesh, and final rectified board.
Keep the source-cell crop and the
actual cleaned OCR input distinct when comparing reads. Some diagnostic paths
reuse the cleaned-input filename for the source crop after an untrusted read.
Use the default Tesseract path when measuring production recognition.
`--ocr-pipeline legacy`, `--ocr-pipeline whole-token`, and `--no-grid-mesh`
support explicit comparisons with earlier recognition or geometry paths.

Approved publisher answer keys provide an independent number check. cdbr
classifies each printed answer letter using templates built from the other
puzzles, converts that letter through the approved symbol mapping, and compares
the resulting number with fresh puzzle OCR. These publisher-derived measurements
remain separate from sparse hand-reviewed truth; they may correct the simulated
HIL lane only when that fresh scan actually requested human review. Reports call
this **oracle-assisted review**: it proves that correct answers at the offered
review gates are sufficient, not that a player will necessarily make them.

Regenerate README, manpage, and Sphinx projections from their canonical sources:

```bash
make docs docs-sync
```

Build and exercise the same container used by the hosted service:

```bash
make container-check
make container-run
```

`make container-check` builds the image and probes its configured health
endpoint. `make container-run` rebuilds and serves it in the foreground at
http://127.0.0.1:8000/.

Merge the intended changes into `main`, bump the version, and commit the
release tree there:

```bash
make release
```

The release target is deliberately interactive in the human sense: it must be
invoked by the maintainer. It runs the full preflight, creates and pushes the
version tag, publishes the GitHub release, and triggers release-driven web
deployment when configured in `pyproject.toml`.

### Photo geometry stress tests

Run the grid detector on a repeatable set of 625 combinations of rotation,
perspective skew, page curl, and scale:

```bash
python -m cdbr.geometry_stress corpus/puzzle_047.jpg > stress.csv
```

Use `--quick` for a short geometry sweep or `--lighting` for 25 combinations
of exposure and a soft shadow. Each row records the transform and whether the
recovered grid has the same size and block layout as the original scan. The
stress test measures geometry independently of number and clue OCR.

### DigitalOcean App Platform example

cdbr uses DigitalOcean App Platform as its first hosted deployment. The app is
connected to the public GitHub repository and builds the repository `Dockerfile`.
Its HTTP service runs `cdbrd`, listens on the platform-supplied `PORT`, and
exposes `/health` for container and platform health checks.

Initial platform setup is deliberately separate from normal releases:

1. Create an App Platform application from the GitHub repository and select the
   repository `Dockerfile` as the build source.
2. Disable App Platform automatic deployment on ordinary source pushes. A push
   to the development branch should not silently become a production release.
3. Record the application identifier as the GitHub Actions repository secret
   `DIGITALOCEAN_APP_ID`.
4. Create a dedicated, least-privilege DigitalOcean API token for this release
   workflow and store it as `DIGITALOCEAN_ACCESS_TOKEN`. Do not reuse a general
   account token.
5. Configure the production domain and any platform environment settings in
   App Platform. `PORT` is supplied by the platform and need not be committed.

The deployment boundary is a published GitHub release—not a routine Git push:

```text
make release
    -> preflight, tests, documentation, and distribution build
    -> push the release commit and annotated version tag
    -> publish the GitHub release
    -> run .github/workflows/release.yml for that tag
    -> verify public installation, tests, container build, and /health
    -> request a forced App Platform rebuild and wait for deployment
```

The workflow reads `tool.npkg.web.deploy-on` from `pyproject.toml`; the
DigitalOcean job runs only for a published GitHub release when that value is
`release`. A manually dispatched workflow performs verification but does not
deploy. Production deployments are serialized, and a failed verification never
calls DigitalOcean.

The GitHub workflow builds and health-checks the production container as an
independent release gate. It does not push that verification image to
DigitalOcean. Instead, `doctl apps create-deployment` tells App Platform to
rebuild its configured source with the same checked-in `Dockerfile`. Because
`make release` pushes the release commit before publishing the tag, the tracked
production branch and released commit are aligned.

### Next steps and future directions

**Operate the current release.** In DigitalOcean App Platform, verify the HTTP
readiness check for `/health` on the service port and enable a liveness probe
with enough consecutive failures to tolerate brief OCR or solver load. Readiness
controls traffic and liveness can restart a stuck instance. Enable failed
deployment and restart-count alerts. Use the Insights graphs for memory and
request duration when investigating scans that slow down. After deployment,
open a corpus puzzle and run one real scan through review and play to exercise
the workflow behind the health endpoint.

**Make game and corpus state durable.** Active games, pending scan jobs, and
newly created puzzles currently live in the server process. A restart or
redeploy can interrupt that work. The packaged corpus ships with the image.
Plan to store game progress, puzzle metadata, and answer keys in SQL, with
source photos and derived images in Spaces. Define stable puzzle identifiers
and publisher provenance before migrating the file corpus. Keep publisher
and book numbers available for lookup. Add an admin review and import workflow
when the storage model is ready.

**Measure scan quality from capture to play.** Keep the difficult Puzzle 47
photos as real-world regressions and use the synthetic sweeps to isolate changes
in perspective, curl, and lighting. Strong curl is the next dewarping target.
Score grid recovery, number and clue accuracy, review burden, retake decisions,
and time separately. Check new thresholds on held-out photos and a second
publisher before treating them as general. Use fresh OCR and solver passes when
measuring the end-to-end experience.

The generated `README.md`, manpages, and files under `docs/sphinx/src/` must not
be edited directly. Update structured source docstrings, `docs/psym/parts/`, or
`docs/psym/templates/`, then regenerate the projections.

System tests require ImageMagick and Tesseract. The project configuration in
`pyproject.toml` is authoritative for Python dependencies and tool settings.

---

## Changelog

### 0.2.5 — 2026-11-26

- Batch reference-clue OCR by Tesseract mode to reduce scan time.
- Flag borderline `6` and `9` reads when the block-mode retry confidently disagrees.
- Flag narrow `4` reads with little crossbar ink. Retry low-ink candidates after trimming the left side of the glyph and suggest a confident `1` for the player to confirm.

### 0.2.4 — 2026-11-26

- Batch board-number OCR by Tesseract mode to reduce process startup overhead during scan review.
- Offer explicit **Load Dictionary** when Play, Scan, or Create needs the British English dictionary. Reuse the loaded dictionary across all three modes and start the scan's solve timer after loading.
- Reveal hints and complete puzzles from certified solutions without flashing the solving overlay. Show progress for longer searches.
- Show the installed version and active dictionary in the **Codewords Breaker** footer.

### 0.2.3 — 2026-11-26

- Add Telegraph puzzles 1–10 to Play alongside the original collection. Choose a puzzle by name or use **Pick one**. Restore the three printed starting clues to original puzzles 71–100.
- Use a shared-vertex mesh and adaptive number crops on both 13×13 and 15×15 scans. Preserve the second digit, remove thin grid-rule remnants, and separate joined digits when the ink supports a split.
- Read both publishers with Tesseract first. Retry weak reads and flag disagreements using repeated numbers from the current photo. Keep historical template banks available for explicit benchmark comparisons.
- Review OCR on the playable board with source numbers, matching-number previews, and a queue for confirmed edits. Inspect any numbered cell, including readings the scanner did not flag.
- Check for a solution when accepting a scan. Distinguish a timeout from a completed search with no solution. Review again, keep searching when more time is available, or play anyway. During play, a second click on a reference cell reveals an available hint directly in both grids.
- Update the OCR guide and pipeline diagram to reflect the shared scan path and the pre-play solution check.

### 0.2.2 — 2026-11-24

- Use JPEG fixtures for Puzzle 47 geometry regression tests so release CI can run them without decoding HEIC.
- Lead the README and user docs with the hosted app at `codebreak.foghub.com` and a gameplay screenshot.

### 0.2.1 — 2026-11-24

- Recover more small, foreshortened, and sideways puzzle grids by checking the internal grid lines after perspective correction.
- Use the sideways reference strip to orient the photo and select the board above it in a two-page shot.
- Ask for a retake when scan quality would leave an unusually large number of cells to review. Show tips for framing, angle, focus, and lighting.
- Retain conflicting clue readings for review and continue when the reference strip cannot supply a complete set of digit templates.
- Add repeatable geometry and lighting stress tests for photographed puzzles.
- Require releases to be made from `main`.

### 0.2.0 — 2026-11-24

- Expand the playable book corpus through puzzle 100 and separate zero-padded puzzle photos, solution photos, audit truth, and playable answer keys.
- Improve whole-number OCR for the 6/8, 16/18, and 9/19 confusions and send uncertain readings to review.
- Run fresh OCR and solver passes in the corpus audit, report progress, and cap each solve attempt at two minutes.
- Improve gameplay navigation with abandon confirmation and a fresh scanner when starting another scan.
- Restore two-click reference hints, warn when a hint comes from a partial result, and use current player entries when solving again.
- Reduce unnecessary blank-clue confirmations and allow revealed entries to be erased.

### 0.1.4

- Added sparse publisher-puzzle packaging and direct book-number selection
- Added human approval of publisher solution keys before solver scoring
- Separated puzzle-number, reference-clue, and publisher-solution OCR audits
- Improved mobile play with a QWERTY keyboard and board-only pinch zoom
- Added the independently generated `cdbrd(1)` service manual

### 0.1.3 — 2026-11-23

- Expanded the photographed 15x15 corpus with matching publisher solutions
- Added error-first, confidence-ordered OCR audit reports
- Added corpus solve inventory and reviewed ground-truth correction support

### 0.1.2 — 2026-11-22

- Added release-driven DigitalOcean App Platform deployment
- Measured OCR accuracy, throughput, review load, and peak memory separately
- Added focused digit-classification benchmarks and 5/6/8 counter adjudication
- Kept expensive corpus benchmarks out of routine deployment verification

### 0.1.1 — 2026-11-20

- Made release CI independent of private npkg development packages
- Installed ImageMagick and Tesseract explicitly in release CI
- Limited Tesseract threading for predictable hosted execution

### 0.1.0 — 2026-11-20

- Recognised photographed puzzles with perspective correction and conservative OCR
- Solved against a British English lexicon with partial-result reporting
- Produced text, TOML, and handwriting-on-photo output
- Generated and independently certified themed 15x15 puzzles
- Added the lightweight scan, create, and play web application

---

## Links

- Documentation: https://tracecutter.github.io/cdbr/
- Source: https://github.com/tracecutter/cdbr
- Issues: https://github.com/tracecutter/cdbr/issues
- Author: https://github.com/tracecutter
