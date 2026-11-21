"""Local, resumable OCR corpus benchmarking."""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import tempfile
import tomllib
from typing import Any

import cdbr.ui as click
import cv2

from cdbr import __version__
from cdbr.core.recognition import WARP_SIZE, RecognitionTrace, _block_mask, _cell_images, recognize_photo


@dataclass(frozen=True, kw_only=True)
class CorpusEntry:
    puzzle_id: int
    photo: Path
    solution: Path


def load_manifest(source: Path) -> tuple[CorpusEntry, ...]:
    """Load and validate a corpus manifest relative to its own directory."""

    with source.open("rb") as stream:
        document = tomllib.load(stream)
    if document.get("format_version") != 1:
        raise ValueError("Unsupported corpus manifest format")
    entries = tuple(
        CorpusEntry(
            puzzle_id=int(item["id"]),
            photo=(source.parent / str(item["photo"])).resolve(),
            solution=(source.parent / str(item["solution"])).resolve(),
        )
        for item in document.get("puzzles", ())
    )
    if not entries:
        raise ValueError("Corpus manifest contains no puzzles")
    identifiers = [entry.puzzle_id for entry in entries]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Corpus manifest contains duplicate puzzle identifiers")
    for entry in entries:
        if not entry.photo.is_file():
            raise ValueError(f"Puzzle photograph does not exist: {entry.photo}")
        if not entry.solution.is_file():
            raise ValueError(f"Puzzle solution does not exist: {entry.solution}")
    return entries


def _digest(source: Path) -> str:
    digest = sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _review_reasons(*, trusted: bool, confidence: float, threshold: float) -> list[str]:
    reasons = []
    if not trusted:
        reasons.append("untrusted")
    if confidence < threshold:
        reasons.append("low-confidence")
    return reasons


def _solution_blocks(source: Path, grid_size: int) -> tuple[bool, ...]:
    image = cv2.imread(str(source))
    if image is None:
        raise ValueError(f"Could not decode solution grid: {source}")
    normalized = cv2.resize(image, (WARP_SIZE, WARP_SIZE), interpolation=cv2.INTER_CUBIC)
    return tuple(_block_mask(_cell_images(normalized, grid_size), grid_size))


def benchmark_entry(
    entry: CorpusEntry,
    work_root: Path,
    review_threshold: float,
) -> dict[str, Any]:
    """Recognise one photograph without invoking the lexical solver."""

    work_dir = work_root / f"puzzle_{entry.puzzle_id:02d}"
    work_dir.mkdir(parents=True, exist_ok=True)
    trace = RecognitionTrace()
    try:
        observation = recognize_photo(entry.photo, work_dir, trace=trace)
        expected_blocks = _solution_blocks(entry.solution, observation.width)
    except Exception as exc:  # noqa: BLE001 - one failed photograph must not stop a corpus run
        return {
            "puzzle_id": entry.puzzle_id,
            "status": "error",
            "photo": str(entry.photo),
            "solution": str(entry.solution),
            "error": f"{type(exc).__name__}: {exc}",
        }

    evidence = sorted(observation.evidence, key=lambda item: (item.row, item.column))
    evidence_payload = [
        {
            "row": item.row,
            "column": item.column,
            "reading": item.reading,
            "confidence": round(item.confidence, 3),
            "trusted": item.trusted,
        }
        for item in evidence
    ]
    review_cells = []
    for item in evidence:
        reasons = _review_reasons(
            trusted=item.trusted,
            confidence=item.confidence,
            threshold=review_threshold,
        )
        if reasons:
            review_cells.append(
                {
                    "row": item.row,
                    "column": item.column,
                    "reading": item.reading,
                    "confidence": round(item.confidence, 3),
                    "reasons": reasons,
                }
            )

    confidences = [item.confidence for item in evidence]
    blocks = sum(value == "." for row in observation.grid for value in row)
    predicted_blocks = tuple(value == "." for row in observation.grid for value in row)
    topology_mismatches = [
        {"row": index // observation.width + 1, "column": index % observation.width + 1}
        for index, (predicted, expected) in enumerate(zip(predicted_blocks, expected_blocks, strict=True))
        if predicted != expected
    ]
    return {
        "format_version": 1,
        "puzzle_id": entry.puzzle_id,
        "status": "ok",
        "photo": str(entry.photo),
        "solution": str(entry.solution),
        "photo_sha256": _digest(entry.photo),
        "cdbr_version": __version__,
        "elapsed_seconds": round(trace.elapsed_seconds, 6),
        "stage_seconds": {name: round(seconds, 6) for name, seconds in trace.stage_seconds.items()},
        "cells": {
            "total": observation.width * observation.height,
            "blocks": blocks,
            "playable": len(evidence),
            "unknown": len(observation.uncertainties),
            "review": len(review_cells),
        },
        "confidence": {
            "minimum": round(min(confidences), 3) if confidences else None,
            "mean": round(statistics.fmean(confidences), 3) if confidences else None,
            "median": round(statistics.median(confidences), 3) if confidences else None,
            "below": {
                str(threshold): sum(confidence < threshold for confidence in confidences)
                for threshold in (55, 60, 65, 70, 75, 80, 85, 90)
            },
        },
        "topology": {
            "correct": observation.width * observation.height - len(topology_mismatches),
            "mismatches": topology_mismatches,
        },
        "clues": observation.clues,
        "clue_evidence": [
            {
                "symbol": item.symbol,
                "reading": item.reading,
                "confidence": round(item.confidence, 3),
            }
            for item in observation.clue_evidence
        ],
        "grid": observation.grid,
        "evidence": evidence_payload,
        "review_cells": review_cells,
    }


def read_results(source: Path) -> list[dict[str, Any]]:
    if not source.exists():
        return []
    return [json.loads(line) for line in source.read_text().splitlines() if line.strip()]


def summarize(results: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    completed = [result for result in results if result.get("status") == "ok"]
    failures = [result for result in results if result.get("status") != "ok"]
    elapsed = [float(result["elapsed_seconds"]) for result in completed]
    return {
        "completed": len(completed),
        "failed": len(failures),
        "seconds": round(sum(elapsed), 3),
        "mean_seconds": round(statistics.fmean(elapsed), 3) if elapsed else 0.0,
        "unknown_cells": sum(int(result["cells"]["unknown"]) for result in completed),
        "review_cells": sum(int(result["cells"]["review"]) for result in completed),
    }


def summarize_classification(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate classification cost separately from photograph preparation."""

    completed = [result for result in results if result.get("status") == "ok"]
    stage_names = sorted(
        {
            name
            for result in completed
            for name in result.get("stage_seconds", {})
            if name == "classify" or name.startswith("classify.")
        }
    )
    stage_totals = {
        name: round(sum(float(result.get("stage_seconds", {}).get(name, 0.0)) for result in completed), 6)
        for name in stage_names
    }
    seconds = stage_totals.get("classify", 0.0)
    cells = sum(int(result.get("cells", {}).get("playable", 0)) for result in completed)
    return {
        "puzzles": len(completed),
        "playable_cells": cells,
        "seconds": seconds,
        "cells_per_second": round(cells / seconds, 3) if seconds else 0.0,
        "stage_seconds": stage_totals,
    }


def resource_usage() -> dict[str, float]:
    """Return portable peak resident-set measurements when available."""

    try:
        import resource
        import sys
    except ImportError:
        return {}
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return {
        "main_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 3),
        "child_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / divisor, 3),
    }


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--manifest",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=Path("examples/corpus.toml"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path(tempfile.gettempdir()) / "cdbr-corpus" / "results.jsonl",
    show_default=True,
)
@click.option(
    "--work-root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path(tempfile.gettempdir()) / "cdbr-corpus" / "work",
    show_default=True,
)
@click.option("--puzzle", "puzzle_ids", type=int, multiple=True, help="Limit the run to one or more puzzle IDs.")
@click.option("--workers", type=click.IntRange(1, 4), default=1, show_default=True)
@click.option("--review-threshold", type=click.FloatRange(0.0, 100.0), default=70.0, show_default=True)
@click.option("--resume/--no-resume", default=True, show_default=True)
def main(
    manifest: Path,
    output: Path,
    work_root: Path,
    puzzle_ids: tuple[int, ...],
    workers: int,
    review_threshold: float,
    resume: bool,
) -> None:
    """Benchmark photograph recognition without running the solver."""

    try:
        entries = load_manifest(manifest.resolve())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    requested = set(puzzle_ids)
    if requested:
        entries = tuple(entry for entry in entries if entry.puzzle_id in requested)
        missing = requested - {entry.puzzle_id for entry in entries}
        if missing:
            raise click.ClickException(f"Puzzle IDs are not in the manifest: {sorted(missing)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    prior = read_results(output) if resume else []
    completed_ids = {int(result["puzzle_id"]) for result in prior if result.get("status") == "ok"}
    pending = [entry for entry in entries if entry.puzzle_id not in completed_ids]
    mode = "a" if resume else "w"
    new_results: list[dict[str, Any]] = []
    with output.open(mode) as stream:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(benchmark_entry, entry, work_root, review_threshold): entry for entry in pending}
            for future in as_completed(futures):
                result = future.result()
                stream.write(json.dumps(result, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                new_results.append(result)
                status = "ok" if result["status"] == "ok" else result["error"]
                click.echo(f"puzzle {result['puzzle_id']}: {status}")

    latest = {int(result["puzzle_id"]): result for result in [*prior, *new_results]}
    summary: dict[str, Any] = {
        **summarize(latest.values()),
        "classification": summarize_classification(latest.values()),
        "resources": resource_usage(),
    }
    click.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
