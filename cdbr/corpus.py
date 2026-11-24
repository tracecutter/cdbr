"""Local, resumable OCR corpus benchmarking."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
import tomllib
from typing import Any
import re

import cdbr.ui as click
import cv2

from cdbr import __version__
from cdbr.corpus_audit import derive_publisher_number_truth, write_audit_reports
from cdbr.core.lexicon import english_lexicon, word_pattern
from cdbr.core.model import CodewordPuzzle, extract_slots
from cdbr.core.puzzle import BLOCK, UNKNOWN
from cdbr.core.recognition import (
    LEGACY_PIPELINE,
    OCR_PIPELINES,
    WARP_SIZE,
    RecognitionTrace,
    _block_mask,
    _cell_images,
    needs_hil_review,
    recognize_photo,
)
from cdbr.core.solver import slot_candidates, solve


@dataclass(frozen=True, kw_only=True)
class CorpusEntry:
    puzzle_id: int
    photo: Path
    solution: Path
    truth: Path | None = None


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
            truth=(source.parent / str(item["truth"])).resolve() if item.get("truth") else None,
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
        if entry.truth is not None and not entry.truth.is_file():
            raise ValueError(f"Puzzle truth does not exist: {entry.truth}")
    return entries


def _truth_document(source: Path) -> dict[str, Any]:
    with source.open("rb") as stream:
        document = tomllib.load(stream)
    if document.get("format_version") != 1:
        raise ValueError(f"Unsupported truth format: {source}")
    return document


def _truth_grid(document: dict[str, Any], source: Path) -> tuple[tuple[int | str, ...], ...]:
    rows = []
    for line in document.get("grid", ()):
        rows.append(tuple("." if token == "##" else int(token) for token in str(line).split()))
    if rows and any(len(row) != len(rows) for row in rows):
        raise ValueError(f"Truth grid must be non-empty and square: {source}")
    return tuple(rows)


def _truth_clues(document: dict[str, Any], source: Path) -> dict[int, str]:
    clues = {int(symbol): str(letter).upper() for symbol, letter in document.get("clues", {}).items()}
    if any(not 1 <= symbol <= 26 or len(letter) != 1 or not letter.isalpha() for symbol, letter in clues.items()):
        raise ValueError(f"Truth clues must map symbols 1-26 to single letters: {source}")
    return clues


def _truth_number_defects(document: dict[str, Any], source: Path) -> dict[tuple[int, int], int]:
    defects = {}
    for coordinate, expected in document.get("number_defects", {}).items():
        match = re.fullmatch(r"r(\d{2})c(\d{2})", str(coordinate))
        if match is None:
            raise ValueError(f"Truth number defect must use rNNcNN coordinates: {source}")
        row, column = (int(value) for value in match.groups())
        symbol = int(expected)
        if not 1 <= symbol <= 26:
            raise ValueError(f"Truth number defects must contain symbols 1-26: {source}")
        defects[row, column] = symbol
    return defects


def _truth_solution(document: dict[str, Any], source: Path) -> dict[int, str]:
    solution = {int(symbol): str(letter).upper() for symbol, letter in document.get("solution", {}).items()}
    if any(not 1 <= symbol <= 26 or len(letter) != 1 or not letter.isalpha() for symbol, letter in solution.items()):
        raise ValueError(f"Truth solution must map symbols 1-26 to single letters: {source}")
    if solution and len(set(solution.values())) != len(solution):
        raise ValueError(f"Truth solution must preserve the letter bijection: {source}")
    return solution


def apply_truth(result: dict[str, Any], source: Path) -> dict[str, Any]:
    """Recalculate accuracy from cached OCR whenever reviewed truth changes."""

    document = _truth_document(source)
    truth = _truth_grid(document, source)
    clue_truth = _truth_clues(document, source)
    number_defects = _truth_number_defects(document, source)
    accept_observed_numbers = bool(document.get("accept_observed_numbers", False))
    if truth and accept_observed_numbers:
        raise ValueError(f"Truth cannot contain both a grid and accept_observed_numbers: {source}")
    observed_grid = result["grid"]
    if truth and (len(truth) != len(observed_grid) or len(truth[0]) != len(observed_grid[0])):
        raise ValueError(f"Truth dimensions do not match puzzle {result['puzzle_id']}")
    evidence = {(int(item["row"]), int(item["column"])): item for item in result["evidence"]}
    mismatches = []
    if truth:
        for row, (observed_row, truth_row) in enumerate(zip(observed_grid, truth, strict=True), 1):
            for column, (observed, expected) in enumerate(zip(observed_row, truth_row, strict=True), 1):
                if expected == "." or observed == expected:
                    continue
                item = evidence.get((row, column))
                observed_reading: int | str = observed
                if item is not None and str(item["reading"]).isdigit():
                    observed_reading = int(item["reading"])
                if observed_reading == expected:
                    continue
                mismatches.append(
                    {
                        "row": row,
                        "column": column,
                        "observed": observed_reading,
                        "expected": expected,
                        "confidence": item["confidence"] if item is not None else None,
                        "trusted": item["trusted"] if item is not None else None,
                    }
                )
    refreshed = dict(result)
    reviewed_defects: list[dict[str, Any]] = []
    if number_defects:
        for (row, column), expected in number_defects.items():
            item = evidence.get((row, column))
            if item is None:
                raise ValueError(f"Truth number defect r{row:02d}c{column:02d} is not a playable cell: {source}")
            reviewed_observed: int | str = observed_grid[row - 1][column - 1]
            if str(item["reading"]).isdigit():
                reviewed_observed = int(item["reading"])
            if reviewed_observed == expected:
                continue
            reviewed_defects.append(
                {
                    "row": row,
                    "column": column,
                    "observed": reviewed_observed,
                    "expected": expected,
                    "confidence": item["confidence"],
                    "trusted": item["trusted"],
                }
            )
        refreshed["number_defects"] = reviewed_defects
    if accept_observed_numbers:
        refreshed["number_accuracy"] = {
            "samples": len(evidence),
            "correct": len(evidence) - len(reviewed_defects),
            "incorrect": len(reviewed_defects),
            "trusted_incorrect": sum(item["trusted"] is True for item in reviewed_defects),
            "mismatches": reviewed_defects,
        }
    if truth:
        total = sum(expected != "." for row in truth for expected in row)
        refreshed["number_accuracy"] = {
            "samples": total,
            "correct": total - len(mismatches),
            "incorrect": len(mismatches),
            "trusted_incorrect": sum(item["trusted"] is True for item in mismatches),
            "mismatches": mismatches,
        }
    if clue_truth:
        observed_clues = {
            int(item["symbol"]): {
                "reading": str(item["reading"]).upper(),
                "confidence": float(item["confidence"]),
            }
            for item in result.get("clue_evidence", ())
        }
        clue_mismatches = []
        for symbol, expected in clue_truth.items():
            observed = observed_clues.get(symbol, {"reading": "", "confidence": 0.0})
            if observed["reading"] != expected:
                clue_mismatches.append(
                    {
                        "symbol": symbol,
                        "observed": observed["reading"],
                        "expected": expected,
                        "confidence": observed["confidence"],
                    }
                )
        false_positives = [
            {
                "symbol": symbol,
                "observed": item["reading"],
                "expected": "",
                "confidence": item["confidence"],
            }
            for symbol, item in observed_clues.items()
            if symbol not in clue_truth
        ]
        refreshed["clue_accuracy"] = {
            "samples": len(clue_truth),
            "correct": len(clue_truth) - len(clue_mismatches),
            "incorrect": len(clue_mismatches),
            "false_positives": len(false_positives),
            "mismatches": [*clue_mismatches, *false_positives],
        }
    return refreshed


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
    ocr_pipeline: str = LEGACY_PIPELINE,
) -> dict[str, Any]:
    """Recognise one photograph without invoking the lexical solver."""

    work_dir = work_root / f"puzzle_{entry.puzzle_id:02d}"
    work_dir.mkdir(parents=True, exist_ok=True)
    trace = RecognitionTrace()
    try:
        observation = recognize_photo(
            entry.photo,
            work_dir,
            trace=trace,
            template_exclusion=entry.puzzle_id,
            ocr_pipeline=ocr_pipeline,
        )
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
    hil_review_cells = []
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
        if needs_hil_review(item):
            hil_review_cells.append(
                {
                    "row": item.row,
                    "column": item.column,
                    "reading": item.reading,
                    "confidence": round(item.confidence, 3),
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
    result = {
        "format_version": 1,
        "puzzle_id": entry.puzzle_id,
        "status": "ok",
        "photo": str(entry.photo),
        "solution": str(entry.solution),
        "photo_sha256": _digest(entry.photo),
        "cdbr_version": __version__,
        "ocr_pipeline": ocr_pipeline,
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
        "hil_review_cells": hil_review_cells,
    }
    return apply_truth(result, entry.truth) if entry.truth is not None else result


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


def summarize_accuracy(results: Iterable[dict[str, Any]], concern: str) -> dict[str, int | float]:
    """Aggregate one independently reviewed OCR concern."""

    key = f"{concern}_accuracy"
    measured = [result[key] for result in results if result.get("status") == "ok" and key in result]
    samples = sum(int(item["samples"]) for item in measured)
    correct = sum(int(item["correct"]) for item in measured)
    incorrect = sum(int(item["incorrect"]) for item in measured)
    summary: dict[str, int | float] = {
        "puzzles": len(measured),
        "samples": samples,
        "correct": correct,
        "incorrect": incorrect,
        "accuracy_percent": round(100.0 * correct / samples, 3) if samples else 0.0,
    }
    if concern == "number":
        summary["trusted_incorrect"] = sum(int(item["trusted_incorrect"]) for item in measured)
    if concern == "clue":
        summary["false_positives"] = sum(int(item["false_positives"]) for item in measured)
    return summary


def summarize_publisher_number_truth(
    derived: Mapping[int, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Score OCR numbers against letters independently read from publisher answer keys."""

    records = [dict(item, puzzle_id=puzzle_id) for puzzle_id, items in derived.items() for item in items]
    mismatches = [item for item in records if int(item["observed"]) != int(item["expected"])]
    correct = len(records) - len(mismatches)
    return {
        "puzzles": len(derived),
        "samples": len(records),
        "correct": correct,
        "incorrect": len(mismatches),
        "accuracy_percent": round(100.0 * correct / len(records), 3) if records else 0.0,
        "mismatches": mismatches,
    }


def benchmark_solutions(
    entries: Iterable[CorpusEntry],
    results: dict[int, dict[str, Any]],
    publisher_number_truth: Mapping[int, Iterable[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Measure scan/HIL and ground-truth search as strictly separate lanes."""

    outcomes = []
    lexicon = english_lexicon()

    def run_search(grid: list[list[int | str]], clues: dict[int, str]) -> dict[str, Any]:
        if any(value not in {BLOCK, "."} and not isinstance(value, int) for row in grid for value in row):
            return {"status": "unresolved-ocr", "mapping": {}, "seconds": 0.0, "nodes": 0, "puzzle": None}
        normalized = tuple(tuple(None if value in {BLOCK, "."} else int(value) for value in row) for row in grid)
        puzzle = CodewordPuzzle(grid=normalized, clues=clues, slots=extract_slots(normalized))
        started = time.perf_counter()
        solved = solve(puzzle, lexicon)
        elapsed = time.perf_counter() - started
        if not solved.solutions:
            status = "contradiction" if solved.exhausted else "search-limited"
            mapping = solved.best_mapping
        elif solved.exhausted and len(solved.solutions) == 1:
            status = "certified"
            mapping = solved.solutions[0].mapping
        elif solved.exhausted:
            status = "multiple"
            mapping = solved.solutions[0].mapping
        else:
            status = "candidate"
            mapping = solved.solutions[0].mapping
        return {
            "status": status,
            "mapping": mapping,
            "seconds": round(elapsed, 3),
            "nodes": solved.nodes,
            "puzzle": puzzle,
        }

    def validate_publisher(puzzle: CodewordPuzzle | None, mapping: dict[int, str]) -> list[dict[str, Any]]:
        if puzzle is None or not mapping:
            return [{"kind": "unavailable-grid"}]
        rejected: list[dict[str, Any]] = []
        for symbol, letter in sorted(puzzle.clues.items()):
            if mapping.get(symbol) != letter:
                rejected.append(
                    {"kind": "clue-mismatch", "symbol": symbol, "expected": letter, "observed": mapping.get(symbol)}
                )
        for slot in puzzle.slots:
            word = "".join(mapping.get(symbol, "?") for symbol in slot.symbols)
            candidates = slot_candidates(slot, lexicon, mapping)
            if any(item.word == word for item in candidates):
                continue
            reason = (
                "incomplete-mapping"
                if "?" in word
                else "pattern-mismatch" if word_pattern(word) != word_pattern(slot.symbols) else "missing-lexicon"
            )
            rejected.append(
                {
                    "kind": "slot-rejected",
                    "slot": slot.index,
                    "direction": slot.direction,
                    "row": slot.row + 1,
                    "column": slot.column + 1,
                    "symbols": list(slot.symbols),
                    "word": word,
                    "reason": reason,
                }
            )
        return rejected

    for entry in entries:
        result = results.get(entry.puzzle_id)
        if result is None or result.get("status") != "ok" or entry.truth is None:
            continue
        truth = _truth_document(entry.truth)
        hil_grid = [list(row) for row in result["grid"]]
        truth_grid = [list(row) for row in result["grid"]]
        reviewed_grid = _truth_grid(truth, entry.truth)
        defects = _truth_number_defects(truth, entry.truth)
        publisher_truth = {
            (int(item["row"]), int(item["column"])): int(item["expected"])
            for item in (publisher_number_truth or {}).get(entry.puzzle_id, ())
        }
        review_positions = {(int(item["row"]), int(item["column"])) for item in result.get("hil_review_cells", ())}
        number_reviews = 0
        number_corrections = 0
        for evidence in result.get("evidence", ()):
            row = int(evidence["row"])
            column = int(evidence["column"])
            reading = str(evidence["reading"])
            expected: int | None = None
            if reviewed_grid:
                reviewed = reviewed_grid[row - 1][column - 1]
                expected = int(reviewed) if reviewed not in {BLOCK, UNKNOWN} else None
            elif (row, column) in defects:
                expected = defects[row, column]
            elif (row, column) in publisher_truth:
                expected = publisher_truth[row, column]
            observed = int(reading) if reading.isdigit() else None
            if expected is not None:
                truth_grid[row - 1][column - 1] = expected
            elif observed is not None and truth_grid[row - 1][column - 1] == UNKNOWN:
                truth_grid[row - 1][column - 1] = observed
            if (row, column) not in review_positions:
                continue
            reviewed_value = expected if expected is not None else observed
            if reviewed_value is not None:
                hil_grid[row - 1][column - 1] = reviewed_value
            number_reviews += 1
            number_corrections += int(observed != reviewed_value)
        if reviewed_grid:
            truth_grid = [list(row) for row in reviewed_grid]
        for (row, column), expected in defects.items():
            truth_grid[row - 1][column - 1] = expected
        for item in (publisher_number_truth or {}).get(entry.puzzle_id, ()):
            truth_grid[int(item["row"]) - 1][int(item["column"]) - 1] = int(item["expected"])

        solution_truth = _truth_solution(truth, entry.truth)
        clue_truth = _truth_clues(truth, entry.truth)
        hil_search = run_search(hil_grid, clue_truth)
        truth_search = run_search(truth_grid, clue_truth)
        publisher_rejections = validate_publisher(hil_search["puzzle"], solution_truth)
        truth_rejections = validate_publisher(truth_search["puzzle"], solution_truth)
        observed_clues = {int(item["symbol"]): str(item["reading"]) for item in result.get("clue_evidence", ())}
        clue_corrections = sum(observed_clues.get(symbol) != letter for symbol, letter in clue_truth.items())
        presumed_hil = bool(number_reviews or clue_corrections)
        outcome_result = (
            "solved-with-presumed-hil"
            if hil_search["status"] in {"certified", "candidate"} and presumed_hil
            else "solved" if hil_search["status"] in {"certified", "candidate"} else "unsolved"
        )
        mismatches = [
            {"symbol": symbol, "observed": hil_search["mapping"].get(symbol), "expected": letter}
            for symbol, letter in sorted(solution_truth.items())
            if hil_search["mapping"].get(symbol) != letter
        ]
        truth_mismatches = [
            {"symbol": symbol, "observed": truth_search["mapping"].get(symbol), "expected": letter}
            for symbol, letter in sorted(solution_truth.items())
            if truth_search["mapping"].get(symbol) != letter
        ]
        outcomes.append(
            {
                "puzzle_id": entry.puzzle_id,
                "status": hil_search["status"],
                "seconds": hil_search["seconds"],
                "nodes": hil_search["nodes"],
                "mapped_symbols": len(hil_search["mapping"]),
                "truth_status": truth_search["status"],
                "truth_seconds": truth_search["seconds"],
                "truth_nodes": truth_search["nodes"],
                "truth_mapped_symbols": len(truth_search["mapping"]),
                "publisher_scored": bool(solution_truth),
                "publisher_playback": "available" if solution_truth else "unavailable",
                "publisher_validation": (
                    "accepted"
                    if solution_truth and not publisher_rejections
                    else "rejected" if solution_truth else "unscored"
                ),
                "publisher_rejections": publisher_rejections,
                "truth_publisher_validation": (
                    "accepted"
                    if solution_truth and not truth_rejections
                    else "rejected" if solution_truth else "unscored"
                ),
                "truth_publisher_rejections": truth_rejections,
                "publisher_match": bool(solution_truth) and not mismatches,
                "publisher_mismatches": mismatches,
                "truth_publisher_match": bool(solution_truth) and not truth_mismatches,
                "truth_publisher_mismatches": truth_mismatches,
                "result": outcome_result,
                "number_reviews": number_reviews,
                "number_corrections": number_corrections,
                "clue_corrections": clue_corrections,
            }
        )
    return {
        "puzzles": len(outcomes),
        "certified": sum(item["status"] == "certified" for item in outcomes),
        "candidate": sum(item["status"] == "candidate" for item in outcomes),
        "multiple": sum(item["status"] == "multiple" for item in outcomes),
        "unsolved": [item["puzzle_id"] for item in outcomes if item["status"] not in {"certified", "candidate"}],
        "solved": sum(item["result"] == "solved" for item in outcomes),
        "solved_with_presumed_hil": sum(item["result"] == "solved-with-presumed-hil" for item in outcomes),
        "publisher_scored": sum(bool(item.get("publisher_scored")) for item in outcomes),
        "publisher_valid": sum(item.get("publisher_validation") == "accepted" for item in outcomes),
        "publisher_rejected": [
            item["puzzle_id"] for item in outcomes if item.get("publisher_validation") == "rejected"
        ],
        "truth_unsolved": [
            item["puzzle_id"] for item in outcomes if item["truth_status"] not in {"certified", "candidate"}
        ],
        "truth_publisher_rejected": [
            item["puzzle_id"] for item in outcomes if item.get("truth_publisher_validation") == "rejected"
        ],
        "publisher_mismatches": [
            item["puzzle_id"] for item in outcomes if item.get("publisher_scored") and not item["publisher_match"]
        ],
        "outcomes": outcomes,
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


def import_solution_approvals(source: Path, entries: Iterable[CorpusEntry]) -> int:
    """Persist a browser-exported publisher-key approval bundle as reviewed truth."""

    bundle = json.loads(source.read_text())
    if not isinstance(bundle, dict):
        raise ValueError("Solution approval bundle must be a JSON object")
    by_id = {entry.puzzle_id: entry for entry in entries}
    written = 0
    for raw_puzzle_id, raw_mapping in bundle.items():
        puzzle_id = int(raw_puzzle_id)
        entry = by_id.get(puzzle_id)
        if entry is None or entry.truth is None:
            raise ValueError(f"Puzzle {puzzle_id} has no truth fixture in the corpus")
        if not isinstance(raw_mapping, dict):
            raise ValueError(f"Puzzle {puzzle_id} solution must be a JSON object")
        mapping = {int(symbol): str(letter).upper() for symbol, letter in raw_mapping.items()}
        if set(mapping) != set(range(1, 27)):
            raise ValueError(f"Puzzle {puzzle_id} solution must contain symbols 1-26")
        if any(len(letter) != 1 or not letter.isalpha() for letter in mapping.values()):
            raise ValueError(f"Puzzle {puzzle_id} solution values must be single letters")
        if len(set(mapping.values())) != 26:
            raise ValueError(f"Puzzle {puzzle_id} solution must contain 26 unique letters")
        text = entry.truth.read_text()
        text = re.sub(r"\n\[solution\]\n(?:[^\[].*\n?)*", "\n", text, flags=re.MULTILINE)
        block = "\n[solution]\n" + "".join(f'"{symbol}" = "{mapping[symbol]}"\n' for symbol in range(1, 27))
        entry.truth.write_text(text.rstrip() + "\n" + block)
        written += 1
    return written


def publish_corpus_assets(
    entries: Iterable[CorpusEntry], results: Mapping[int, Mapping[str, Any]], destination: Path
) -> list[int]:
    """Build sparse, release-ready puzzles only from human-approved solution truth."""

    destination.mkdir(parents=True, exist_ok=True)
    published = []
    for entry in entries:
        result = results.get(entry.puzzle_id)
        if result is None or result.get("status") != "ok" or entry.truth is None:
            continue
        truth = _truth_document(entry.truth)
        solution = _truth_solution(truth, entry.truth)
        if set(solution) != set(range(1, 27)):
            continue
        grid = [list(row) for row in result["grid"]]
        reviewed_grid = _truth_grid(truth, entry.truth)
        if reviewed_grid:
            grid = [list(row) for row in reviewed_grid]
        elif truth.get("accept_observed_numbers") is True:
            # Human review accepted the photographed grid except for the
            # explicit defects below. Restore conservative OCR proposals that
            # were withheld from the public grid solely for HIL confirmation.
            for evidence in result.get("evidence", ()):
                row = int(evidence["row"])
                column = int(evidence["column"])
                reading = str(evidence["reading"])
                if grid[row - 1][column - 1] == UNKNOWN and reading.isdigit():
                    grid[row - 1][column - 1] = int(reading)
        for (row, column), expected in _truth_number_defects(truth, entry.truth).items():
            grid[row - 1][column - 1] = expected
        if any(value not in {BLOCK, "."} and not isinstance(value, int) for row in grid for value in row):
            continue
        clues = _truth_clues(truth, entry.truth)
        lines = [
            "format_version = 1",
            f"serial = {entry.puzzle_id}",
            'origin = "publisher"',
            "",
            "grid = [",
            *(f'  "{" ".join("##" if value in {BLOCK, "."} else str(value) for value in row)}",' for row in grid),
            "]",
            "",
            "[clues]",
            *(f'"{symbol}" = "{letter}"' for symbol, letter in sorted(clues.items())),
            "",
            "[solution]",
            *(f'"{symbol}" = "{solution[symbol]}"' for symbol in range(1, 27)),
            "",
        ]
        (destination / f"puzzle-{entry.puzzle_id}.toml").write_text("\n".join(lines))
        published.append(entry.puzzle_id)
    return published


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--manifest",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=Path("examples/corpus.toml"),
    show_default=True,
)
@click.option("--publish-assets/--no-publish-assets", default=False, help="Build packaged puzzles from approved truth.")
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
@click.option("--ocr-pipeline", type=click.Choice(OCR_PIPELINES), default=LEGACY_PIPELINE, show_default=True)
@click.option("--summary-output", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--resume/--no-resume", default=True, show_default=True)
@click.option("--audit/--no-audit", default=False, help="Write separate number and clue OCR review reports.")
@click.option("--solve/--no-solve", "solve_corpus", default=False, help="Solve reviewed grids and inventory outcomes.")
@click.option(
    "--import-solution-approvals",
    "import_solution_approvals_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Import the JSON bundle downloaded from the publisher-solution approval gate.",
)
@click.option(
    "--audit-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("build/corpus-audit"),
    show_default=True,
)
def main(
    manifest: Path,
    output: Path,
    work_root: Path,
    puzzle_ids: tuple[int, ...],
    workers: int,
    review_threshold: float,
    ocr_pipeline: str,
    summary_output: Path | None,
    resume: bool,
    audit: bool,
    solve_corpus: bool,
    import_solution_approvals_path: Path | None,
    publish_assets: bool,
    audit_dir: Path,
) -> None:
    """Benchmark photograph recognition, optionally inventorying solve outcomes."""

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

    if import_solution_approvals_path is not None:
        try:
            count = import_solution_approvals(import_solution_approvals_path, entries)
        except (ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Imported {count} approved publisher solution mappings.")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    prior = read_results(output) if resume else []
    completed_ids = {int(result["puzzle_id"]) for result in prior if result.get("status") == "ok"}
    pending = [entry for entry in entries if entry.puzzle_id not in completed_ids]
    mode = "a" if resume else "w"
    new_results: list[dict[str, Any]] = []
    with output.open(mode) as stream:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(benchmark_entry, entry, work_root, review_threshold, ocr_pipeline): entry
                for entry in pending
            }
            for future in as_completed(futures):
                result = future.result()
                stream.write(json.dumps(result, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                new_results.append(result)
                status = "ok" if result["status"] == "ok" else result["error"]
                click.echo(f"puzzle {result['puzzle_id']}: {status}")

    entry_ids = {entry.puzzle_id for entry in entries}
    latest = {
        int(result["puzzle_id"]): result for result in [*prior, *new_results] if int(result["puzzle_id"]) in entry_ids
    }
    for entry in entries:
        if entry.truth is not None and entry.puzzle_id in latest and latest[entry.puzzle_id].get("status") == "ok":
            latest[entry.puzzle_id] = apply_truth(latest[entry.puzzle_id], entry.truth)
    publisher_number_truth = derive_publisher_number_truth(entries, latest)
    summary: dict[str, Any] = {
        "ocr_pipeline": ocr_pipeline,
        **summarize(latest.values()),
        "number_ocr": summarize_accuracy(latest.values(), "number"),
        "clue_ocr": summarize_accuracy(latest.values(), "clue"),
        "publisher_number_ocr": summarize_publisher_number_truth(publisher_number_truth),
        "classification": summarize_classification(latest.values()),
        "resources": resource_usage(),
    }
    if solve_corpus:
        summary["solutions"] = benchmark_solutions(entries, latest, publisher_number_truth)
        for outcome in summary["solutions"]["outcomes"]:
            result = latest[int(outcome["puzzle_id"])]
            cells = result["cells"]
            number_accuracy = result.get("number_accuracy", {})
            click.echo(
                "puzzle "
                f"{outcome['puzzle_id']}: parsed {cells['playable']} cells; "
                f"{cells['unknown']} unknown; {cells['review']} review; "
                f"{number_accuracy.get('incorrect', 0)} known OCR errors; "
                f"{number_accuracy.get('trusted_incorrect', 0)} trusted wrong; "
                f"publisher playback {outcome['publisher_playback']}; "
                f"publisher validation {outcome['publisher_validation']} "
                f"({len(outcome['publisher_rejections'])} rejected constraints); "
                f"scan/HIL search {outcome['status']}; "
                f"ground-truth search {outcome['truth_status']}"
            )
    if publish_assets:
        summary["published_assets"] = publish_corpus_assets(
            entries,
            latest,
            Path(__file__).parent / "assets" / "puzzles",
        )
    click.echo(json.dumps(summary, indent=2))
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if audit:
        target = write_audit_reports(
            entries=entries,
            results=latest,
            work_root=work_root,
            destination=audit_dir,
            review_threshold=review_threshold,
            number_summary=summary["number_ocr"],
            clue_summary=summary["clue_ocr"],
            solution_summary=summary.get("solutions"),
            publisher_number_truth=publisher_number_truth,
        )
        click.echo(f"Corpus audit: {target}")


if __name__ == "__main__":
    main()
