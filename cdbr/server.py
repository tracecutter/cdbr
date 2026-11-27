"""HTTP service entry point for the cdbr solving pipeline.

[[daemon.meta.title]]
cdbrd

[[daemon.meta.tagline]]
Serve the Code Break web application and HTTP API.

[[daemon.section.overview]]
cdbrd runs the lightweight HTTP service used by the Code Break browser
application. Choose a named puzzle from either collection in Play, or use
Pick one to open a random board. Packaged puzzles open with their printed
starting letters. The service also scans photographed puzzles and constructs
new ones using the same engines as the cdbr command-line program.

Sessions, uploaded photographs, scan-review jobs, and generated candidates are
ephemeral. They remain in memory or temporary storage only for the lifetime of
the service; cdbrd does not require a database. CLI solving does not require
cdbrd to be running.

[[daemon.section.deployment]]
For local use, bind to the loopback interface:

```bash
cdbrd --host 127.0.0.1 --port 8000
```

Container platforms normally supply `PORT` through the environment. cdbrd runs
one Uvicorn worker because generation jobs and puzzle sessions currently live
inside the service process. The `--reload` option is for local development only.

The `/health` endpoint reports service status and the installed cdbr version.

[[daemon.environment.port]]
HTTP port on which the service listens. An explicit `--port` value takes
precedence. The default is 8000.

[[daemon.environment.host]]
Address on which the service listens. An explicit `--host` value takes
precedence. The default is 0.0.0.0.

[[daemon.section.examples]]
Run a local preview restricted to the current computer:

```bash
cdbrd --host 127.0.0.1 --port 8000
```

Run with source reloading during development:

```bash
cdbrd --host 127.0.0.1 --reload
```

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved.
:license: MIT, see LICENSE for details.
"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import time
import tomllib
from typing import Annotated, Literal

import cdbr.ui as click
import cv2
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from cdbr import __version__
from cdbr.core.exceptions import CdbrCoreError
from cdbr.core.generator import GeneratedPuzzle, GenerationLimits, generate_puzzle
from cdbr.core.lexicon import Lexicon, english_lexicon
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.pipeline import solve_observation, solve_photo
from cdbr.core.puzzle import BLOCK, PuzzleObservation
from cdbr.core.presentation import write_solution_photo
from cdbr.core.recognition import (
    MIN_CLUE_REVIEW_INK_PIXELS,
    RecognitionTrace,
    clue_ink_pixels,
    needs_hil_review,
    normalize_photo,
    recognize_photo,
)

DEFAULT_MAX_UPLOAD_MIB = 25
CHUNK_SIZE = 1024 * 1024
WEB_ROOT = Path(__file__).parent / "assets" / "web"
PUZZLE_ROOT = Path(__file__).parent / "assets" / "puzzles"
MAX_SESSIONS = 100
MAX_GENERATION_JOBS = 20
MAX_SCAN_JOBS = 20
MIN_RETAKE_REVIEW_CELLS = 20
MAX_SCAN_REVIEW_FRACTION = 0.25
SCAN_SOLVE_SECONDS = 10.0
SCAN_SOLVE_RETRY_SECONDS = (30.0, 120.0)
SCAN_DICTIONARY_LABEL = "British English"
_scan_lexicon: Lexicon | None = None
_scan_lexicon_lock = threading.Lock()


def _scan_solution_lexicon() -> Lexicon:
    global _scan_lexicon
    with _scan_lexicon_lock:
        if _scan_lexicon is None:
            _scan_lexicon = english_lexicon()
        return _scan_lexicon


@dataclass(kw_only=True)
class PuzzleSession:
    session_id: str
    puzzle: dict[str, object]
    solution: dict[int, str] | None = None
    observation: PuzzleObservation | None = None
    solution_status: str = "not_requested"
    solve_entries: tuple[tuple[int, str], ...] = ()
    solve_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def public(self) -> dict[str, object]:
        return {
            **self.puzzle,
            "session_id": self.session_id,
            "solution_status": self.solution_status,
        }


class CreatePuzzleRequest(BaseModel):
    required_words: list[str] = Field(min_length=1, max_length=8)
    excluded_words: list[str] = Field(default_factory=list, max_length=30)
    minutes: float = Field(default=5, ge=0.25, le=30)


class SolveRequest(BaseModel):
    entries: dict[int, str] = Field(default_factory=dict, max_length=26)


class CellCorrection(BaseModel):
    row: int = Field(ge=1, le=15)
    column: int = Field(ge=1, le=15)
    value: int = Field(ge=1, le=26)


class ClueCorrection(BaseModel):
    symbol: int = Field(ge=1, le=26)
    letter: str = Field(pattern=r"^[A-Za-z]?$", description="A confirmed letter, or blank for an empty reference cell")


class ScanCorrectionRequest(BaseModel):
    cells: list[CellCorrection] = Field(default_factory=list, max_length=225)
    clues: list[ClueCorrection] = Field(default_factory=list, max_length=26)
    check_solution: bool = False
    search_round: int = Field(default=0, ge=0, le=len(SCAN_SOLVE_RETRY_SECONDS))


@dataclass(frozen=True, kw_only=True)
class ScanJob:
    job_id: str
    work_dir: Path
    observation: PuzzleObservation
    review_clues: tuple[tuple[int, int], ...]


@dataclass(kw_only=True)
class GenerationJob:
    job_id: str
    request: CreatePuzzleRequest
    status: str = "queued"
    progress: str = "Waiting to start…"
    created_at: float = field(default_factory=time.monotonic)
    cancelled: bool = False
    accepted: bool = False
    generated: GeneratedPuzzle | None = None
    certified_candidates: int = 0
    deadline: float | None = None
    error: str | None = None
    published_serial: int | None = None


_sessions: OrderedDict[str, PuzzleSession] = OrderedDict()
_runtime_corpus: dict[int, tuple[dict[str, object], dict[int, str]]] = {}
_generation_jobs: OrderedDict[str, GenerationJob] = OrderedDict()
_scan_jobs: OrderedDict[str, ScanJob] = OrderedDict()
_generation_lock = threading.Lock()
_generation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cdbr-generator")

app = FastAPI(
    title="cdbr",
    description="Solve photographed Code Break puzzles.",
    version=__version__,
)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    page = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{ app_version }}", __version__)
    return HTMLResponse(page.replace("{{ dictionary_label }}", SCAN_DICTIONARY_LABEL))


@app.get("/favicon.png", response_class=FileResponse, include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB_ROOT / "f-logo.png")


def _playable_puzzle(puzzle_id: str) -> tuple[dict[str, object], dict[int, str] | None]:
    telegraph = puzzle_id.startswith("telegraph-")
    try:
        serial = int(puzzle_id.removeprefix("telegraph-"))
    except ValueError:
        raise HTTPException(status_code=404, detail="Puzzle not found") from None
    if not telegraph and serial in _runtime_corpus:
        return _runtime_corpus[serial]
    collection = "telegraph" if telegraph else "puzzle"
    source_path = PUZZLE_ROOT / f"{collection}-{serial}.toml"
    if not telegraph and serial == 1:
        source_path = PUZZLE_ROOT / "seed-437.toml"
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Puzzle not found")
    with source_path.open("rb") as stream:
        source = tomllib.load(stream)
    grid: list[list[int | None]] = [
        [None if value == "##" else int(value) for value in str(row).split()] for row in source["grid"]
    ]
    private_root = Path(os.environ.get("CDBR_SOLUTIONS_DIR", "solutions/playable"))
    private_path = private_root / f"{collection}_{serial:03d}.toml"
    if not private_path.is_file():
        private_path = private_root / source_path.name
    answers = source
    if private_path.is_file():
        with private_path.open("rb") as stream:
            answers = tomllib.load(stream)
    solution = None
    if "solution" in answers:
        solution = {int(symbol): str(letter).upper() for symbol, letter in answers["solution"].items()}
    elif "answer" in answers:
        answer = tuple(str(row) for row in answers["answer"])
        solution = {
            symbol: letter
            for symbols, letters in zip(grid, answer, strict=True)
            for symbol, letter in zip(symbols, letters, strict=True)
            if symbol is not None
        }
    if solution is not None:
        solution = _complete_mapping(solution)
    clues = {int(symbol): str(letter) for symbol, letter in source["clues"].items()}
    used_symbols = sorted({symbol for row in grid for symbol in row if symbol is not None})
    puzzle: dict[str, object] = {
        "id": f"telegraph-{serial}" if telegraph else str(serial),
        "serial": serial,
        "title": f"Telegraph {serial}" if telegraph else f"Puzzle {serial}",
        "grid": grid,
        "clues": clues,
        "symbols": list(range(1, 27)),
        "used_symbols": used_symbols,
    }
    return puzzle, solution


def _packaged_corpus_ids(collection: str = "puzzle") -> list[int]:
    identifiers = [1] if collection == "puzzle" and (PUZZLE_ROOT / "seed-437.toml").is_file() else []
    prefix = f"{collection}-"
    for source in PUZZLE_ROOT.glob(f"{prefix}*.toml"):
        try:
            identifiers.append(int(source.stem.removeprefix(prefix)))
        except ValueError:
            continue
    return sorted(set(identifiers))


def _complete_mapping(mapping: dict[int, str]) -> dict[int, str]:
    solution = dict(mapping)
    unused_symbols = sorted(set(range(1, 27)) - solution.keys())
    unused_letters = sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - set(solution.values()))
    solution.update(zip(unused_symbols, unused_letters, strict=True))
    return solution


def _create_session(
    puzzle: dict[str, object],
    solution: dict[int, str] | None = None,
    *,
    observation: PuzzleObservation | None = None,
) -> PuzzleSession:
    session_id = secrets.token_urlsafe(12)
    session = PuzzleSession(
        session_id=session_id,
        puzzle=puzzle,
        solution=solution,
        observation=observation,
        solution_status="certified" if solution is not None else "not_requested",
    )
    _sessions[session_id] = session
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
    return session


def _session(session_id: str) -> PuzzleSession:
    try:
        return _sessions[session_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Puzzle session not found or expired") from None


def _solve_entries(session: PuzzleSession, entries: dict[int, str]) -> tuple[tuple[int, str], ...]:
    normalized = tuple(sorted((symbol, letter.upper()) for symbol, letter in entries.items()))
    if any(not 1 <= symbol <= 26 or len(letter) != 1 or not letter.isalpha() for symbol, letter in normalized):
        raise HTTPException(status_code=422, detail="Solver entries must map symbols 1–26 to single letters.")
    letters = [letter for _, letter in normalized]
    if len(letters) != len(set(letters)):
        raise HTTPException(status_code=422, detail="Each letter may be assigned to only one symbol.")
    raw_clues = session.puzzle.get("clues", {})
    if not isinstance(raw_clues, dict):
        raise HTTPException(status_code=500, detail="Puzzle clues are invalid.")
    original = {int(symbol): str(letter).upper() for symbol, letter in raw_clues.items()}
    if any(symbol in original and original[symbol] != letter for symbol, letter in normalized):
        raise HTTPException(status_code=422, detail="Original puzzle clues cannot be changed.")
    if any(letter in original.values() and original.get(symbol) != letter for symbol, letter in normalized):
        raise HTTPException(status_code=422, detail="A letter from an original clue cannot be reused.")
    return normalized


def _solve_session(session: PuzzleSession, entries: dict[int, str] | None = None) -> None:
    """Populate a session solution on demand without invalidating play on failure."""

    requested = _solve_entries(session, entries or {})
    if (
        session.solution_status == "certified"
        and not session.solve_entries
        and all((session.solution or {}).get(symbol) == letter for symbol, letter in requested)
    ):
        return
    if (session.observation is None and session.solution_status == "certified") or (
        session.solution_status != "not_requested" and requested == session.solve_entries
    ):
        return
    with session.solve_lock:
        if (session.observation is None and session.solution_status == "certified") or (
            session.solution_status != "not_requested" and requested == session.solve_entries
        ):
            return
        session.solve_entries = requested
        if session.observation is None:
            session.solution = {}
            session.solution_status = "unavailable"
            return
        clues = {**session.observation.clues, **dict(requested)}
        observation = replace(session.observation, clues=clues)
        try:
            solved = solve_observation(observation, _scan_solution_lexicon())
        except (CdbrCoreError, ValueError):
            session.solution = clues
            session.solution_status = "unavailable"
            return
        session.solution = dict(solved.mapping)
        if solved.result.exhausted and len(solved.result.solutions) == 1:
            session.solution_status = "certified"
            if session.puzzle.get("provenance") == "corpus":
                session.solution = _complete_mapping(session.solution)
        elif solved.result.solutions:
            session.solution_status = "candidate"
        elif session.solution:
            session.solution_status = "partial"
        else:
            session.solution_status = "unavailable"


def _scan_job(job_id: str) -> ScanJob:
    try:
        return _scan_jobs[job_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Scan review not found or expired") from None


def _remember_scan(job: ScanJob) -> None:
    _scan_jobs[job.job_id] = job
    while len(_scan_jobs) > MAX_SCAN_JOBS:
        _, expired = _scan_jobs.popitem(last=False)
        shutil.rmtree(expired.work_dir, ignore_errors=True)


def _scan_public(job: ScanJob) -> dict[str, object]:
    review = []
    for item in job.observation.evidence:
        if not needs_hil_review(item):
            continue
        proposed = int(item.reading) if item.reading.isdigit() and 1 <= int(item.reading) <= 26 else None
        review.append(
            {
                "row": item.row,
                "column": item.column,
                "proposed": proposed,
                "confidence": round(item.confidence, 1),
                "reason": "unrecognised" if proposed is None else "needs confirmation",
                "image": f"/api/scan-jobs/{job.job_id}/cells/{item.row}/{item.column}",
            }
        )
    clue_evidence = {item.symbol: item for item in job.observation.clue_evidence}
    review_clues = []
    review_ink = dict(job.review_clues)
    for symbol in review_ink:
        clue_item = clue_evidence.get(symbol)
        review_clues.append(
            {
                "symbol": symbol,
                "proposed": (clue_item.reading or None) if clue_item is not None else None,
                "confidence": round(clue_item.confidence, 1) if clue_item is not None else 0.0,
                "ink_pixels": review_ink[symbol],
                "image": f"/api/scan-jobs/{job.job_id}/clues/{symbol}",
            }
        )
    return {
        "job_id": job.job_id,
        "status": "review" if review or review_clues else "ready",
        "grid": [list(row) for row in job.observation.grid],
        "clues": job.observation.clues,
        "review_cells": review,
        "review_clues": review_clues,
    }


@app.post("/api/sessions/from-corpus/{puzzle_id}", status_code=201)
def corpus_session_endpoint(puzzle_id: str) -> dict[str, object]:
    if puzzle_id == "random":
        puzzle_id = secrets.choice([str(puzzle.get("id", puzzle["serial"])) for puzzle in _corpus_catalog()])
    return _create_corpus_session(puzzle_id).public()


def _create_corpus_session(puzzle_id: str) -> PuzzleSession:
    puzzle, solution = _playable_puzzle(puzzle_id)
    observation = None
    if solution is None:
        grid = puzzle["grid"]
        clues = puzzle["clues"]
        asset = f"{puzzle['id']}.toml" if puzzle_id.startswith("telegraph-") else f"puzzle-{puzzle['id']}.toml"
        assert isinstance(grid, list) and isinstance(clues, dict)
        observation = PuzzleObservation(
            source=PUZZLE_ROOT / asset,
            source_format="TOML",
            grid=tuple(tuple(BLOCK if value is None else value for value in row) for row in grid),
            clues=clues,
            uncertainties=(),
        )
    return _create_session({**puzzle, "provenance": "corpus"}, solution, observation=observation)


@app.get("/api/sessions/{session_id}")
def session_endpoint(session_id: str) -> dict[str, object]:
    return _session(session_id).public()


@app.post("/api/sessions/{session_id}/reveal/{symbol}")
def session_reveal_endpoint(session_id: str, symbol: int, request: SolveRequest | None = None) -> dict[str, str | int]:
    session = _session(session_id)
    _solve_session(session, request.entries if request else None)
    solution = session.solution or {}
    if symbol not in solution:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The puzzle is solved. Number {symbol} has no letter in this grid."
                if session.solution_status == "certified"
                else f"No hint is available for number {symbol} yet. Your entries are unchanged."
            ),
        )
    return {"symbol": symbol, "letter": solution[symbol], "solution_status": session.solution_status}


@app.post("/api/sessions/{session_id}/reveal")
def session_reveal_all_endpoint(session_id: str, request: SolveRequest | None = None) -> dict[str, object]:
    session = _session(session_id)
    _solve_session(session, request.entries if request else None)
    return {
        "mapping": session.solution or {},
        "solution_status": session.solution_status,
        "complete": session.solution_status == "certified",
    }


@app.post("/api/sessions/{session_id}/check")
def session_check_endpoint(session_id: str, request: SolveRequest) -> dict[str, object]:
    """Check committed player entries without revealing their replacements."""

    session = _session(session_id)
    entries = _solve_entries(session, request.entries)
    _solve_session(session)
    solution = session.solution or {}
    checked = [symbol for symbol, _ in entries if symbol in solution]
    incorrect = [symbol for symbol, letter in entries if solution.get(symbol) != letter and symbol in solution]
    return {
        "checked_symbols": checked,
        "incorrect_symbols": incorrect,
        "solution_status": session.solution_status,
    }


class GenerationCancelled(Exception):
    """Internal signal used to stop a cooperative generation job."""


def _generation_job(job_id: str) -> GenerationJob:
    try:
        return _generation_jobs[job_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Generation job not found or expired") from None


def _generation_job_public(job: GenerationJob) -> dict[str, object]:
    payload: dict[str, object] = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "elapsed_seconds": round(time.monotonic() - job.created_at),
        "remaining_seconds": max(0, round(job.deadline - time.monotonic())) if job.deadline is not None else None,
    }
    if job.error is not None:
        payload["error"] = job.error
    if job.generated is not None:
        blocks = sum(symbol is None for row in job.generated.puzzle.grid for symbol in row)
        payload["candidate"] = {
            "black_cells": blocks,
            "clues": len(job.generated.puzzle.clues),
            "seed": job.generated.seed,
            "certified_candidates": job.certified_candidates,
        }
    if job.published_serial is not None:
        payload["published_serial"] = job.published_serial
    return payload


def _generated_quality(generated: GeneratedPuzzle) -> tuple[float, float, float]:
    """Rank candidates by open cells, then weakest and average vocabulary."""

    blocks = sum(symbol is None for row in generated.puzzle.grid for symbol in row)
    scores: list[float] = []
    if generated.certification.solutions:
        scores = [entry.score for entry in generated.certification.solutions[0].words.values()]
    return (-float(blocks), min(scores, default=0.0), sum(scores) / len(scores) if scores else 0.0)


def _run_generation_job(job: GenerationJob) -> None:
    with _generation_lock:
        if job.cancelled:
            job.status = "cancelled"
            job.progress = "Cancelled"
            return
        job.status = "running"
        job.progress = "Loading the British English lexicon…"
        job.deadline = time.monotonic() + job.request.minutes * 60

    def progress(message: str) -> None:
        with _generation_lock:
            if job.cancelled:
                raise GenerationCancelled
            job.progress = message

    try:
        lexicon = _scan_solution_lexicon()
        while job.deadline is not None:
            remaining = job.deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                generated = generate_puzzle(
                    lexicon,
                    seed=secrets.randbits(31),
                    limits=GenerationLimits(
                        attempts=1_000,
                        seconds=remaining,
                        clue_count=3,
                    ),
                    progress=progress,
                    required_words=job.request.required_words,
                    excluded_words=job.request.excluded_words,
                )
            except ValueError:
                break
            with _generation_lock:
                if job.cancelled:
                    raise GenerationCancelled
                job.certified_candidates += 1
                if job.generated is None or _generated_quality(generated) > _generated_quality(job.generated):
                    job.generated = generated
                    blocks = sum(symbol is None for row in generated.puzzle.grid for symbol in row)
                    job.progress = f"New best: {blocks} black cells"
    except GenerationCancelled:
        with _generation_lock:
            if not job.accepted:
                job.status = "cancelled"
                job.progress = "Cancelled"
    except Exception:
        with _generation_lock:
            job.status = "failed"
            job.progress = "Generation failed unexpectedly"
            job.error = "The generator encountered an unexpected error"
    else:
        with _generation_lock:
            if job.accepted:
                return
            if job.generated is None:
                job.status = "failed"
                job.progress = "No certified puzzle was found"
                job.error = "No certified puzzle found within the generation limits"
            else:
                job.status = "complete"
                job.progress = "Best certified puzzle ready"


@app.post("/api/generation-jobs", status_code=202)
def create_generation_job_endpoint(request: CreatePuzzleRequest) -> dict[str, object]:
    with _generation_lock:
        if len(_generation_jobs) >= MAX_GENERATION_JOBS:
            expired = next(
                (
                    job_id
                    for job_id, job in _generation_jobs.items()
                    if job.status in {"accepted", "complete", "failed", "cancelled"}
                ),
                None,
            )
            if expired is None:
                raise HTTPException(status_code=429, detail="Too many generation jobs are already active")
            del _generation_jobs[expired]
        job = GenerationJob(job_id=secrets.token_urlsafe(9), request=request)
        _generation_jobs[job.job_id] = job
    _generation_executor.submit(_run_generation_job, job)
    return _generation_job_public(job)


@app.get("/api/generation-jobs/{job_id}")
def generation_job_endpoint(job_id: str) -> dict[str, object]:
    return _generation_job_public(_generation_job(job_id))


@app.post("/api/generation-jobs/{job_id}/cancel")
def cancel_generation_job_endpoint(job_id: str) -> dict[str, object]:
    job = _generation_job(job_id)
    with _generation_lock:
        if job.status in {"queued", "running"}:
            job.cancelled = True
            job.progress = "Cancelling…"
    return _generation_job_public(job)


@app.post("/api/generation-jobs/{job_id}/publish", status_code=201)
def publish_generation_job_endpoint(job_id: str) -> dict[str, object]:
    job = _generation_job(job_id)
    with _generation_lock:
        if job.generated is None or job.status not in {"running", "complete", "accepted"}:
            raise HTTPException(status_code=409, detail="The generation job has no certified puzzle to publish")
        if job.status == "running":
            job.accepted = True
            job.cancelled = True
            job.status = "accepted"
            job.progress = "Best candidate accepted"
        if job.published_serial is None:
            serial = max((*_packaged_corpus_ids(), *_runtime_corpus.keys())) + 1
            generated = job.generated
            grid = [list(row) for row in generated.puzzle.grid]
            puzzle: dict[str, object] = {
                "id": str(serial),
                "serial": serial,
                "title": f"Puzzle {serial}",
                "grid": grid,
                "clues": generated.puzzle.clues,
                "symbols": list(range(1, 27)),
                "used_symbols": sorted({symbol for row in grid for symbol in row if symbol is not None}),
                "origin": "cdbr_generated",
            }
            _runtime_corpus[serial] = (puzzle, _complete_mapping(generated.mapping))
            job.published_serial = serial
        puzzle, solution = _runtime_corpus[job.published_serial]
    return _create_session({**puzzle, "provenance": "corpus"}, solution).public()


def _corpus_catalog() -> list[dict[str, int | str]]:
    serials = sorted(set(_packaged_corpus_ids()) | set(_runtime_corpus))
    catalog: list[dict[str, int | str]] = [{"serial": serial, "title": f"Puzzle {serial}"} for serial in serials]
    for serial in _packaged_corpus_ids("telegraph"):
        catalog.append({"id": f"telegraph-{serial}", "serial": serial, "title": f"Telegraph {serial}"})
    return catalog


@app.get("/api/puzzles")
def puzzles_endpoint() -> dict[str, object]:
    return {"puzzles": _corpus_catalog()}


@app.get("/api/puzzles/{puzzle_id}")
def puzzle_endpoint(puzzle_id: str) -> dict[str, object]:
    puzzle, _ = _playable_puzzle(puzzle_id)
    return puzzle


@app.post("/api/puzzles/{puzzle_id}/reveal/{symbol}")
def reveal_endpoint(puzzle_id: str, symbol: int) -> dict[str, str | int]:
    session = _create_corpus_session(puzzle_id)
    _solve_session(session)
    solution = session.solution or {}
    if symbol not in solution:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"symbol": symbol, "letter": solution[symbol]}


@app.post("/api/puzzles/{puzzle_id}/reveal")
def reveal_all_endpoint(puzzle_id: str) -> dict[str, dict[int, str]]:
    session = _create_corpus_session(puzzle_id)
    _solve_session(session)
    return {"mapping": session.solution or {}}


def _max_upload_bytes() -> int:
    value = int(os.environ.get("CDBR_MAX_UPLOAD_MIB", DEFAULT_MAX_UPLOAD_MIB))
    return value * 1024 * 1024


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    maximum = _max_upload_bytes()
    written = 0
    with destination.open("wb") as stream:
        while chunk := await upload.read(CHUNK_SIZE):
            written += len(chunk)
            if written > maximum:
                raise HTTPException(
                    status_code=413, detail=f"Photograph exceeds the {maximum // 1024 // 1024} MiB limit"
                )
            stream.write(chunk)
    if not written:
        raise HTTPException(status_code=400, detail="Photograph is empty")


@app.post("/api/photo-preview", response_class=Response)
async def photo_preview_endpoint(photo: Annotated[UploadFile, File()]) -> Response:
    """Return a browser-displayable preview for formats such as HEIC."""

    suffix = Path(photo.filename or "upload").suffix.lower()
    if suffix not in {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        suffix = ".img"
    with tempfile.TemporaryDirectory(prefix="cdbr-preview-") as directory:
        work_dir = Path(directory)
        source = work_dir / f"upload{suffix}"
        destination = work_dir / "preview.jpg"
        await _save_upload(photo, source)
        try:
            if detect_photo_format(source) is PhotoFormat.UNKNOWN:
                raise ValueError("Unsupported or unrecognised image format")
            normalize_photo(source, destination, maximum_size=1400)
        except (CdbrCoreError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(content=destination.read_bytes(), media_type="image/jpeg")


class _ScanMemory:
    """Sample Linux cgroup memory across the scan, including OCR subprocesses."""

    def __init__(self) -> None:
        self.current = Path("/sys/fs/cgroup/memory.current")
        self.maximum = Path("/sys/fs/cgroup/memory.max")
        if not self.current.is_file():
            self.current = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            self.maximum = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        self.start_bytes = self._read(self.current)
        self.peak_bytes = self.start_bytes
        self.limit_bytes = self._read(self.maximum)
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._sample_until_stopped)
        if self.start_bytes is not None:
            self.worker.start()

    @staticmethod
    def _read(path: Path) -> int | None:
        try:
            return int(path.read_text())
        except (OSError, ValueError):
            return None

    def _sample(self) -> None:
        sample = self._read(self.current)
        if sample is not None:
            self.peak_bytes = max(self.peak_bytes or 0, sample)

    def _sample_until_stopped(self) -> None:
        while not self.stop.wait(0.02):
            self._sample()

    def finish(self) -> None:
        if self.start_bytes is not None:
            self.stop.set()
            self.worker.join()
            self._sample()


@app.post("/api/scan-jobs", status_code=201)
async def scan_job_endpoint(
    photo: Annotated[UploadFile, File()],
    response: Response,
    x_cdbr_scan_timing: Annotated[str | None, Header()] = None,
    x_cdbr_scan_ocr: Annotated[Literal["tesseract", "helvetica", "helvetica-deferred"] | None, Header()] = None,
) -> dict[str, object]:
    """Recognise a photograph and pause before solving when cells need review."""

    trace = RecognitionTrace() if x_cdbr_scan_timing == "1" else None
    scan_started = time.perf_counter() if trace is not None else 0.0
    suffix = Path(photo.filename or "upload").suffix.lower()
    if suffix not in {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        suffix = ".img"
    work_dir = Path(tempfile.mkdtemp(prefix="cdbr-scan-"))
    source = work_dir / f"upload{suffix}"
    memory = _ScanMemory() if trace is not None else None
    try:
        await _save_upload(photo, source)
        if detect_photo_format(source) is PhotoFormat.UNKNOWN:
            raise ValueError("Unsupported or unrecognised image format")
        ocr_mode = x_cdbr_scan_ocr or os.getenv("CDBR_SCAN_OCR", "helvetica")
        if trace is not None:
            trace.record("prepare", scan_started)
        if ocr_mode in {"helvetica", "helvetica-deferred"}:
            observation = recognize_photo(
                source,
                work_dir,
                trace=trace,
                helvetica_first=True,
                match_deferred_only=ocr_mode == "helvetica-deferred",
            )
        elif trace is not None:
            observation = recognize_photo(source, work_dir, trace=trace)
        else:
            observation = recognize_photo(source, work_dir)
        review_started = time.perf_counter() if trace is not None else 0.0
        review_cells = [item for item in observation.evidence if needs_hil_review(item)]
        if len(review_cells) >= MIN_RETAKE_REVIEW_CELLS and len(review_cells) > MAX_SCAN_REVIEW_FRACTION * len(
            observation.evidence
        ):
            raise ValueError(
                f"Too many grid numbers are unclear ({len(review_cells)} need review). Please retake the photo."
            )
        grid_image = cv2.imread(str(work_dir / "grid.png"))
        reference_grid = cv2.imread(str(work_dir / "reference-grid.png"))
        if grid_image is None:
            raise ValueError("Could not prepare cell review images")
        if reference_grid is None:
            raise ValueError("Could not prepare reference-grid review images")
        clue_symbols = {item.symbol for item in observation.clue_evidence}
        review_clues = []
        for symbol in range(1, 27):
            row = 0 if symbol <= 13 else 1
            column = (symbol - 1) % 13
            cell = reference_grid[row * 100 : (row + 1) * 100, column * 100 : (column + 1) * 100]
            ink_pixels = clue_ink_pixels(cell)
            if symbol in clue_symbols or ink_pixels >= MIN_CLUE_REVIEW_INK_PIXELS:
                review_clues.append((symbol, ink_pixels))
    except (CdbrCoreError, ValueError) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if memory is not None:
            memory.finish()

    job = ScanJob(
        job_id=secrets.token_urlsafe(12),
        work_dir=work_dir,
        observation=observation,
        review_clues=tuple(review_clues),
    )
    _remember_scan(job)
    payload = _scan_public(job)
    if trace is not None:
        trace.record("review", review_started)
        trace.stage_seconds["recognition"] = trace.elapsed_seconds
        trace.record("scan", scan_started)
        response.headers["Server-Timing"] = ", ".join(
            f"{name};dur={seconds * 1000:.1f}" for name, seconds in trace.stage_seconds.items()
        )
    if memory is not None and memory.peak_bytes is not None:
        response.headers["X-CDBR-Scan-Memory"] = f"start={memory.start_bytes}, peak={memory.peak_bytes}" + (
            f", limit={memory.limit_bytes}" if memory.limit_bytes is not None else ""
        )
    return payload


def _scan_crop(source: Path, row: int, column: int, rows: int, columns: int) -> Response:
    image = cv2.imread(str(source))
    if image is None:
        raise HTTPException(status_code=404, detail="Review image not found")
    height, width = image.shape[:2]
    cell = image[
        round((row - 1) * height / rows) : round(row * height / rows),
        round((column - 1) * width / columns) : round(column * width / columns),
    ]
    success, jpeg = cv2.imencode(".jpg", cell)
    if not success:
        raise HTTPException(status_code=500, detail="Could not prepare review image")
    return Response(jpeg.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/scan-jobs/{job_id}/grid", response_class=Response)
def scan_grid_endpoint(job_id: str) -> Response:
    job = _scan_job(job_id)
    grid = cv2.imread(str(job.work_dir / "grid.png"))
    if grid is None:
        raise HTTPException(status_code=404, detail="Review image not found")
    preview = cv2.resize(grid, (900, 900), interpolation=cv2.INTER_AREA)
    success, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        raise HTTPException(status_code=500, detail="Could not prepare review image")
    return Response(jpeg.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/scan-jobs/{job_id}/cells/{row}/{column}", response_class=Response)
def scan_cell_endpoint(job_id: str, row: int, column: int) -> Response:
    job = _scan_job(job_id)
    board = job.observation
    if not (1 <= row <= board.height and 1 <= column <= board.width) or board.grid[row - 1][column - 1] == BLOCK:
        raise HTTPException(status_code=404, detail="Review cell not found")
    return _scan_crop(job.work_dir / "grid.png", row, column, board.height, board.width)


@app.get("/api/scan-jobs/{job_id}/clues/{symbol}", response_class=Response)
def scan_clue_endpoint(job_id: str, symbol: int) -> Response:
    job = _scan_job(job_id)
    if not 1 <= symbol <= 26:
        raise HTTPException(status_code=404, detail="Reference clue not found")
    row, column = divmod(symbol - 1, 13)
    return _scan_crop(job.work_dir / "reference-grid.png", row + 1, column + 1, 2, 13)


@app.get("/api/scan-dictionary")
def scan_dictionary_status() -> dict[str, bool]:
    return {"loaded": _scan_lexicon is not None}


@app.post("/api/scan-dictionary")
def load_scan_dictionary(language: Literal["en-GB"] = "en-GB") -> dict[str, bool]:
    _scan_solution_lexicon()
    return {"loaded": True}


@app.post("/api/scan-jobs/{job_id}/complete", status_code=201)
def complete_scan_endpoint(job_id: str, request: ScanCorrectionRequest) -> dict[str, object]:
    """Apply reviewed OCR values and optionally check for a solution before play."""

    job = _scan_job(job_id)
    required = {(item.row, item.column) for item in job.observation.evidence if needs_hil_review(item)}
    corrections = {(item.row, item.column): item.value for item in request.cells}
    missing = required - corrections.keys()
    if missing:
        coordinates = ", ".join(f"r{row:02d}c{column:02d}" for row, column in sorted(missing))
        raise HTTPException(status_code=422, detail=f"Confirm every review cell: {coordinates}")
    required_clues = {symbol for symbol, _ in job.review_clues}
    reviewed_clues = {item.symbol: item.letter.upper() for item in request.clues}
    missing_clues = required_clues - reviewed_clues.keys()
    if missing_clues:
        symbols = ", ".join(str(symbol) for symbol in sorted(missing_clues))
        raise HTTPException(status_code=422, detail=f"Confirm every reference clue: {symbols}")
    clue_corrections = {
        symbol: letter for symbol, letter in {**job.observation.clues, **reviewed_clues}.items() if letter
    }
    if len(set(clue_corrections.values())) != len(clue_corrections):
        raise HTTPException(status_code=422, detail="Reference clues must use different letters")

    grid = [list(row) for row in job.observation.grid]
    for (row, column), value in corrections.items():
        if row > job.observation.height or column > job.observation.width or grid[row - 1][column - 1] == BLOCK:
            raise HTTPException(status_code=422, detail=f"Cell r{row:02d}c{column:02d} is not a numbered square")
        grid[row - 1][column - 1] = value
    corrected = PuzzleObservation(
        source=job.observation.source,
        source_format=job.observation.source_format,
        grid=tuple(tuple(row) for row in grid),
        clues=clue_corrections,
        uncertainties=(),
        evidence=job.observation.evidence,
        clue_evidence=job.observation.clue_evidence,
    )

    playable_grid = [[None if value == BLOCK else int(value) for value in row] for row in corrected.grid]
    used_symbols = sorted({symbol for row in playable_grid for symbol in row if symbol is not None})
    puzzle: dict[str, object] = {
        "title": "Scanned puzzle",
        "grid": playable_grid,
        "clues": corrected.clues,
        "symbols": list(range(1, 27)),
        "used_symbols": used_symbols,
        "provenance": "photo",
    }
    solved = None
    if request.check_solution:
        budgets = (SCAN_SOLVE_SECONDS, *SCAN_SOLVE_RETRY_SECONDS)
        try:
            lexicon = _scan_solution_lexicon()
            deadline = time.monotonic() + budgets[request.search_round]
            solved = solve_observation(corrected, lexicon, deadline=deadline)
        except (CdbrCoreError, ValueError):
            pass
        if solved is None or not solved.complete:
            if solved is None:
                status = "unavailable"
            elif solved.result.exhausted:
                status = "no_complete_solution"
            elif time.monotonic() >= deadline:
                status = "time_limit"
            else:
                status = "search_limit"
            next_round = request.search_round + 1
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "scan_solve_check",
                    "status": status,
                    "next_search_round": next_round if status == "time_limit" and next_round < len(budgets) else None,
                },
            )
    session = _create_session(puzzle, observation=corrected)
    if solved is not None:
        session.solution = dict(solved.mapping)
        session.solution_status = (
            "certified" if solved.result.exhausted and len(solved.result.solutions) == 1 else "candidate"
        )
    _scan_jobs.pop(job_id, None)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    return session.public()


@app.post("/api/sessions/from-photo")
async def photo_session_endpoint(photo: Annotated[UploadFile, File()]) -> None:
    """Reject the legacy scan shortcut so every upload passes through fresh HIL."""

    del photo
    raise HTTPException(
        status_code=410,
        detail="Direct photo sessions are retired; create a fresh /api/scan-jobs review instead",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/solve", response_class=Response)
async def solve_endpoint(photo: Annotated[UploadFile, File()]) -> Response:
    suffix = Path(photo.filename or "upload").suffix.lower()
    if suffix not in {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        suffix = ".img"

    with tempfile.TemporaryDirectory(prefix="cdbr-http-") as directory:
        work_dir = Path(directory)
        source = work_dir / f"upload{suffix}"
        destination = work_dir / "solution.jpg"
        await _save_upload(photo, source)
        try:
            if detect_photo_format(source) is PhotoFormat.UNKNOWN:
                raise ValueError("Unsupported or unrecognised image format")
            solved = solve_photo(source, work_dir)
            write_solution_photo(source, destination, solved.puzzle, solved.mapping, work_dir)
        except (CdbrCoreError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        status = "complete" if solved.complete else "partial"
        return Response(
            content=destination.read_bytes(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": 'inline; filename="solution.jpg"',
                "X-Cdbr-Solution": status,
                "X-Cdbr-Solutions-Found": str(len(solved.result.solutions)),
                "X-Cdbr-Search-Exhausted": str(solved.result.exhausted).lower(),
            },
        )


@click.command(name="cdbrd", context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--host",
    default="0.0.0.0",
    show_default=True,
    envvar="CDBR_HOST",
    help="Address on which the HTTP service listens.",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=click.IntRange(1, 65535),
    envvar="PORT",
    help="HTTP port; may also be supplied through PORT.",
)
@click.option("--reload", is_flag=True, help="Reload when Python source files change.")
def cdbrd_main(host: str, port: int, reload: bool) -> None:
    """Run the local cdbr web application and HTTP API."""

    uvicorn.run("cdbr.server:app", host=host, port=port, reload=reload, workers=1)


def main() -> None:
    cdbrd_main()


if __name__ == "__main__":
    main()
