"""HTTP service entry point for the cdbr solving pipeline."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import tomllib
from typing import Annotated

import cdbr.ui as click
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from cdbr import __version__
from cdbr.core.exceptions import CdbrCoreError
from cdbr.core.generator import GeneratedPuzzle, GenerationLimits, generate_puzzle
from cdbr.core.lexicon import english_lexicon
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.pipeline import solve_photo
from cdbr.core.presentation import write_solution_photo
from cdbr.core.recognition import normalize_photo

DEFAULT_MAX_UPLOAD_MIB = 25
CHUNK_SIZE = 1024 * 1024
WEB_ROOT = Path(__file__).parent / "assets" / "web"
PUZZLE_ROOT = Path(__file__).parent / "assets" / "puzzles"
MAX_SESSIONS = 100
MAX_GENERATION_JOBS = 20


@dataclass(frozen=True, kw_only=True)
class PuzzleSession:
    session_id: str
    puzzle: dict[str, object]
    solution: dict[int, str]

    def public(self) -> dict[str, object]:
        return {**self.puzzle, "session_id": self.session_id}


class CreatePuzzleRequest(BaseModel):
    required_words: list[str] = Field(min_length=1, max_length=8)
    excluded_words: list[str] = Field(default_factory=list, max_length=30)
    minutes: float = Field(default=5, ge=0.25, le=30)


@dataclass(kw_only=True)
class GenerationJob:
    job_id: str
    request: CreatePuzzleRequest
    status: str = "queued"
    progress: str = "Waiting to start…"
    created_at: float = field(default_factory=time.monotonic)
    cancelled: bool = False
    generated: GeneratedPuzzle | None = None
    error: str | None = None
    published_serial: int | None = None


_sessions: OrderedDict[str, PuzzleSession] = OrderedDict()
_runtime_corpus: dict[int, tuple[dict[str, object], dict[int, str]]] = {}
_generation_jobs: OrderedDict[str, GenerationJob] = OrderedDict()
_generation_lock = threading.Lock()
_generation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cdbr-generator")

app = FastAPI(
    title="cdbr",
    description="Solve photographed Code Break puzzles.",
    version=__version__,
)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", response_class=FileResponse, include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/favicon.png", response_class=FileResponse, include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB_ROOT / "f-logo.png")


def _playable_puzzle(puzzle_id: str) -> tuple[dict[str, object], dict[int, str]]:
    if puzzle_id != "1":
        try:
            return _runtime_corpus[int(puzzle_id)]
        except (KeyError, ValueError):
            raise HTTPException(status_code=404, detail="Puzzle not found") from None
    with (PUZZLE_ROOT / "seed-437.toml").open("rb") as stream:
        source = tomllib.load(stream)
    grid: list[list[int | None]] = [
        [None if value == "##" else int(value) for value in str(row).split()] for row in source["grid"]
    ]
    answer = tuple(str(row) for row in source["answer"])
    solution = {
        symbol: letter
        for symbols, letters in zip(grid, answer, strict=True)
        for symbol, letter in zip(symbols, letters, strict=True)
        if symbol is not None
    }
    unused_symbols = sorted(set(range(1, 27)) - solution.keys())
    unused_letters = sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - set(solution.values()))
    solution.update(zip(unused_symbols, unused_letters, strict=True))
    clues = {int(symbol): str(letter) for symbol, letter in source["clues"].items()}
    used_symbols = sorted({symbol for row in grid for symbol in row if symbol is not None})
    puzzle: dict[str, object] = {
        "id": puzzle_id,
        "serial": 1,
        "title": "Puzzle 1",
        "grid": grid,
        "clues": clues,
        "symbols": list(range(1, 27)),
        "used_symbols": used_symbols,
    }
    return puzzle, solution


def _complete_mapping(grid: list[list[int | None]], mapping: dict[int, str]) -> dict[int, str]:
    solution = dict(mapping)
    unused_symbols = sorted(set(range(1, 27)) - solution.keys())
    unused_letters = sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - set(solution.values()))
    solution.update(zip(unused_symbols, unused_letters, strict=True))
    return solution


def _create_session(puzzle: dict[str, object], solution: dict[int, str]) -> PuzzleSession:
    session_id = secrets.token_urlsafe(12)
    session = PuzzleSession(session_id=session_id, puzzle=puzzle, solution=solution)
    _sessions[session_id] = session
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
    return session


def _session(session_id: str) -> PuzzleSession:
    try:
        return _sessions[session_id]
    except KeyError:
        raise HTTPException(status_code=404, detail="Puzzle session not found or expired") from None


@app.post("/api/sessions/from-corpus/{puzzle_id}", status_code=201)
def corpus_session_endpoint(puzzle_id: str) -> dict[str, object]:
    puzzle, solution = _playable_puzzle(puzzle_id)
    return _create_session({**puzzle, "provenance": "corpus"}, solution).public()


@app.get("/api/sessions/{session_id}")
def session_endpoint(session_id: str) -> dict[str, object]:
    return _session(session_id).public()


@app.post("/api/sessions/{session_id}/reveal/{symbol}")
def session_reveal_endpoint(session_id: str, symbol: int) -> dict[str, str | int]:
    session = _session(session_id)
    if symbol not in session.solution:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"symbol": symbol, "letter": session.solution[symbol]}


@app.post("/api/sessions/{session_id}/reveal")
def session_reveal_all_endpoint(session_id: str) -> dict[str, dict[int, str]]:
    return {"mapping": _session(session_id).solution}


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
    }
    if job.error is not None:
        payload["error"] = job.error
    if job.generated is not None:
        blocks = sum(symbol is None for row in job.generated.puzzle.grid for symbol in row)
        payload["candidate"] = {
            "black_cells": blocks,
            "clues": len(job.generated.puzzle.clues),
            "seed": job.generated.seed,
        }
    if job.published_serial is not None:
        payload["published_serial"] = job.published_serial
    return payload


def _run_generation_job(job: GenerationJob) -> None:
    with _generation_lock:
        if job.cancelled:
            job.status = "cancelled"
            job.progress = "Cancelled"
            return
        job.status = "running"
        job.progress = "Loading the British English lexicon…"

    def progress(message: str) -> None:
        with _generation_lock:
            if job.cancelled:
                raise GenerationCancelled
            job.progress = message

    try:
        generated = generate_puzzle(
            english_lexicon(),
            seed=secrets.randbits(31),
            limits=GenerationLimits(
                attempts=1_000,
                seconds=job.request.minutes * 60,
                clue_count=3,
            ),
            progress=progress,
            required_words=job.request.required_words,
            excluded_words=job.request.excluded_words,
        )
    except GenerationCancelled:
        with _generation_lock:
            job.status = "cancelled"
            job.progress = "Cancelled"
    except ValueError as exc:
        with _generation_lock:
            job.status = "failed"
            job.progress = "No certified puzzle was found"
            job.error = str(exc)
    except Exception:
        with _generation_lock:
            job.status = "failed"
            job.progress = "Generation failed unexpectedly"
            job.error = "The generator encountered an unexpected error"
    else:
        with _generation_lock:
            job.generated = generated
            job.status = "complete"
            job.progress = "Certified puzzle ready"


@app.post("/api/generation-jobs", status_code=202)
def create_generation_job_endpoint(request: CreatePuzzleRequest) -> dict[str, object]:
    with _generation_lock:
        if len(_generation_jobs) >= MAX_GENERATION_JOBS:
            expired = next(
                (
                    job_id
                    for job_id, job in _generation_jobs.items()
                    if job.status in {"complete", "failed", "cancelled"}
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
        if job.status != "complete" or job.generated is None:
            raise HTTPException(status_code=409, detail="The generation job has no certified puzzle to publish")
        if job.published_serial is None:
            serial = max((1, *_runtime_corpus.keys())) + 1
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
            _runtime_corpus[serial] = (puzzle, _complete_mapping(grid, generated.mapping))
            job.published_serial = serial
        puzzle, solution = _runtime_corpus[job.published_serial]
    return _create_session({**puzzle, "provenance": "corpus"}, solution).public()


@app.get("/api/puzzles/{puzzle_id}")
def puzzle_endpoint(puzzle_id: str) -> dict[str, object]:
    puzzle, _ = _playable_puzzle(puzzle_id)
    return puzzle


@app.post("/api/puzzles/{puzzle_id}/reveal/{symbol}")
def reveal_endpoint(puzzle_id: str, symbol: int) -> dict[str, str | int]:
    _, solution = _playable_puzzle(puzzle_id)
    if symbol not in solution:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"symbol": symbol, "letter": solution[symbol]}


@app.post("/api/puzzles/{puzzle_id}/reveal")
def reveal_all_endpoint(puzzle_id: str) -> dict[str, dict[int, str]]:
    _, solution = _playable_puzzle(puzzle_id)
    return {"mapping": solution}


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


@app.post("/api/sessions/from-photo", status_code=201)
async def photo_session_endpoint(photo: Annotated[UploadFile, File()]) -> dict[str, object]:
    suffix = Path(photo.filename or "upload").suffix.lower()
    if suffix not in {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        suffix = ".img"
    with tempfile.TemporaryDirectory(prefix="cdbr-http-") as directory:
        work_dir = Path(directory)
        source = work_dir / f"upload{suffix}"
        await _save_upload(photo, source)
        try:
            if detect_photo_format(source) is PhotoFormat.UNKNOWN:
                raise ValueError("Unsupported or unrecognised image format")
            solved = solve_photo(source, work_dir)
            if not solved.result.exhausted or len(solved.result.solutions) != 1:
                raise ValueError("The photographed puzzle could not be certified with one unique solution")
        except (CdbrCoreError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    grid = [list(row) for row in solved.puzzle.grid]
    used_symbols = sorted({symbol for row in grid for symbol in row if symbol is not None})
    puzzle: dict[str, object] = {
        "title": "Scanned puzzle",
        "grid": grid,
        "clues": solved.puzzle.clues,
        "symbols": list(range(1, 27)),
        "used_symbols": used_symbols,
        "provenance": "photo",
    }
    solution = _complete_mapping(grid, solved.mapping)
    return _create_session(puzzle, solution).public()


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


@click.command(name="cdbrd")
@click.option("--host", default="0.0.0.0", show_default=True, envvar="CDBR_HOST")
@click.option("--port", default=8000, show_default=True, type=click.IntRange(1, 65535), envvar="PORT")
@click.option("--reload", is_flag=True, help="Reload when Python source files change.")
def cdbrd_main(host: str, port: int, reload: bool) -> None:
    """Run the cdbr HTTP service."""

    uvicorn.run("cdbr.server:app", host=host, port=port, reload=reload, workers=1)


def main() -> None:
    cdbrd_main()


if __name__ == "__main__":
    main()
