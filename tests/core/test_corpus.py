"""Tests for resumable local corpus benchmarking."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import cdbr.corpus as corpus_module
from cdbr.corpus import (
    CorpusEntry,
    apply_truth,
    benchmark_solutions,
    load_manifest,
    summarize,
    summarize_accuracy,
    summarize_classification,
)
from cdbr.corpus_audit import write_audit_reports


def test_load_manifest_resolves_assets_relative_to_manifest(tmp_path: Path) -> None:
    (tmp_path / "photo.jpg").touch()
    (tmp_path / "solution.jpg").touch()
    manifest = tmp_path / "corpus.toml"
    manifest.write_text('format_version = 1\n[[puzzles]]\nid = 31\nphoto = "photo.jpg"\nsolution = "solution.jpg"\n')

    entries = load_manifest(manifest)

    assert len(entries) == 1
    assert entries[0].puzzle_id == 31
    assert entries[0].photo == (tmp_path / "photo.jpg").resolve()
    assert entries[0].solution == (tmp_path / "solution.jpg").resolve()
    assert entries[0].truth is None


def test_load_manifest_resolves_optional_truth(tmp_path: Path) -> None:
    (tmp_path / "photo.jpg").touch()
    (tmp_path / "solution.jpg").touch()
    (tmp_path / "truth.toml").write_text('format_version = 1\ngrid = ["01"]\n')
    manifest = tmp_path / "corpus.toml"
    manifest.write_text(
        'format_version = 1\n[[puzzles]]\nid = 31\nphoto = "photo.jpg"\n'
        'solution = "solution.jpg"\ntruth = "truth.toml"\n'
    )

    entries = load_manifest(manifest)

    assert entries[0].truth == (tmp_path / "truth.toml").resolve()


def test_load_manifest_rejects_duplicate_identifiers(tmp_path: Path) -> None:
    (tmp_path / "photo.jpg").touch()
    (tmp_path / "solution.jpg").touch()
    manifest = tmp_path / "corpus.toml"
    manifest.write_text(
        "format_version = 1\n"
        '[[puzzles]]\nid = 31\nphoto = "photo.jpg"\nsolution = "solution.jpg"\n'
        '[[puzzles]]\nid = 31\nphoto = "photo.jpg"\nsolution = "solution.jpg"\n'
    )

    with pytest.raises(ValueError, match="duplicate puzzle identifiers"):
        load_manifest(manifest)


def test_summarize_counts_review_load_and_failures() -> None:
    summary = summarize(
        [
            {
                "status": "ok",
                "elapsed_seconds": 2.5,
                "cells": {"unknown": 2, "review": 5},
            },
            {
                "status": "ok",
                "elapsed_seconds": 1.5,
                "cells": {"unknown": 0, "review": 3},
            },
            {"status": "error"},
        ]
    )

    assert summary == {
        "completed": 2,
        "failed": 1,
        "seconds": 4.0,
        "mean_seconds": 2.0,
        "unknown_cells": 2,
        "review_cells": 8,
    }


def test_summarize_classification_reports_throughput_and_substages() -> None:
    summary = summarize_classification(
        [
            {
                "status": "ok",
                "cells": {"playable": 150},
                "stage_seconds": {
                    "classify": 1.5,
                    "classify.reference": 0.5,
                    "classify.audit": 1.0,
                },
            },
            {
                "status": "ok",
                "cells": {"playable": 100},
                "stage_seconds": {
                    "classify": 1.0,
                    "classify.reference": 0.4,
                    "classify.audit": 0.6,
                },
            },
            {"status": "error"},
        ]
    )

    assert summary == {
        "puzzles": 2,
        "playable_cells": 250,
        "seconds": 2.5,
        "cells_per_second": 100.0,
        "stage_seconds": {
            "classify": 2.5,
            "classify.audit": 1.6,
            "classify.reference": 0.9,
        },
    }


def test_summarize_accuracy_keeps_number_and_clue_concerns_separate() -> None:
    source = [
        {
            "status": "ok",
            "number_accuracy": {"samples": 225, "correct": 223, "incorrect": 2, "trusted_incorrect": 2},
            "clue_accuracy": {"samples": 3, "correct": 2, "incorrect": 1, "false_positives": 1},
        },
        {"status": "ok"},
        {"status": "error"},
    ]

    assert summarize_accuracy(source, "number") == {
        "puzzles": 1,
        "samples": 225,
        "correct": 223,
        "incorrect": 2,
        "accuracy_percent": 99.111,
        "trusted_incorrect": 2,
    }
    assert summarize_accuracy(source, "clue") == {
        "puzzles": 1,
        "samples": 3,
        "correct": 2,
        "incorrect": 1,
        "accuracy_percent": 66.667,
        "false_positives": 1,
    }


def test_apply_truth_refreshes_cached_accuracy(tmp_path: Path) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\ngrid = ["01 02", "## 04"]\n[clues]\n"1" = "A"\n"2" = "B"\n')
    result = {
        "puzzle_id": 31,
        "grid": [[1, 3], [".", 4]],
        "evidence": [
            {"row": 1, "column": 1, "reading": "1", "confidence": 90.0, "trusted": True},
            {"row": 1, "column": 2, "reading": "3", "confidence": 80.0, "trusted": True},
            {"row": 2, "column": 2, "reading": "4", "confidence": 60.0, "trusted": False},
        ],
        "clue_evidence": [
            {"symbol": 1, "reading": "A", "confidence": 100.0},
            {"symbol": 2, "reading": "D", "confidence": 33.333},
        ],
        "number_accuracy": {"incorrect": 99},
    }

    refreshed = apply_truth(result, truth)

    assert refreshed["number_accuracy"] == {
        "samples": 3,
        "correct": 2,
        "incorrect": 1,
        "trusted_incorrect": 1,
        "mismatches": [
            {
                "row": 1,
                "column": 2,
                "observed": 3,
                "expected": 2,
                "confidence": 80.0,
                "trusted": True,
            }
        ],
    }
    assert refreshed["clue_accuracy"]["samples"] == 2
    assert refreshed["clue_accuracy"]["correct"] == 1
    assert refreshed["clue_accuracy"]["incorrect"] == 1
    assert refreshed["clue_accuracy"]["false_positives"] == 0
    assert refreshed["clue_accuracy"]["mismatches"] == [
        {"symbol": 2, "observed": "D", "expected": "B", "confidence": 33.333}
    ]
    assert result["number_accuracy"] == {"incorrect": 99}


def test_apply_truth_accepts_clue_only_fixture(tmp_path: Path) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\n[clues]\n"14" = "X"\n')
    result = {
        "puzzle_id": 47,
        "grid": [[1]],
        "evidence": [{"row": 1, "column": 1, "reading": "1", "confidence": 90.0, "trusted": True}],
        "clue_evidence": [{"symbol": 14, "reading": "A", "confidence": 66.667}],
    }

    refreshed = apply_truth(result, truth)

    assert "number_accuracy" not in refreshed
    assert refreshed["clue_accuracy"] == {
        "samples": 1,
        "correct": 0,
        "incorrect": 1,
        "false_positives": 0,
        "mismatches": [{"symbol": 14, "observed": "A", "expected": "X", "confidence": 66.667}],
    }


def test_apply_truth_records_sparse_human_confirmed_number_defects(tmp_path: Path) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\n[number_defects]\n"r01c02" = 16\n')
    result = {
        "puzzle_id": 37,
        "grid": [[1, 18]],
        "evidence": [
            {"row": 1, "column": 1, "reading": "1", "confidence": 90.0, "trusted": True},
            {"row": 1, "column": 2, "reading": "18", "confidence": 59.0, "trusted": False},
        ],
        "clue_evidence": [],
    }

    refreshed = apply_truth(result, truth)

    assert "number_accuracy" not in refreshed
    assert refreshed["number_defects"] == [
        {
            "row": 1,
            "column": 2,
            "observed": 18,
            "expected": 16,
            "confidence": 59.0,
            "trusted": False,
        }
    ]


def test_apply_truth_accepts_remaining_observed_numbers_as_reviewed(tmp_path: Path) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\naccept_observed_numbers = true\n[number_defects]\n"r01c02" = 16\n')
    result = {
        "puzzle_id": 37,
        "grid": [[1, 18]],
        "evidence": [
            {"row": 1, "column": 1, "reading": "1", "confidence": 90.0, "trusted": True},
            {"row": 1, "column": 2, "reading": "18", "confidence": 59.0, "trusted": False},
        ],
        "clue_evidence": [],
    }

    refreshed = apply_truth(result, truth)

    assert refreshed["number_accuracy"] == {
        "samples": 2,
        "correct": 1,
        "incorrect": 1,
        "trusted_incorrect": 0,
        "mismatches": refreshed["number_defects"],
    }


def test_apply_truth_counts_a_corrected_number_defect_as_correct(tmp_path: Path) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\naccept_observed_numbers = true\n[number_defects]\n"r01c02" = 16\n')
    result = {
        "puzzle_id": 37,
        "grid": [[1, 16]],
        "evidence": [
            {"row": 1, "column": 1, "reading": "1", "confidence": 90.0, "trusted": True},
            {"row": 1, "column": 2, "reading": "16", "confidence": 80.0, "trusted": True},
        ],
        "clue_evidence": [],
    }

    refreshed = apply_truth(result, truth)

    assert refreshed["number_defects"] == []
    assert refreshed["number_accuracy"]["correct"] == 2
    assert refreshed["number_accuracy"]["incorrect"] == 0


def test_benchmark_solutions_scores_only_confirmed_publisher_mapping(tmp_path: Path, monkeypatch) -> None:
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\n[clues]\n"1" = "A"\n[solution]\n"1" = "A"\n"2" = "B"\n')
    entry = CorpusEntry(puzzle_id=1, photo=tmp_path / "puzzle.jpg", solution=tmp_path / "solution.jpg", truth=truth)
    solved = SimpleNamespace(
        solutions=(SimpleNamespace(mapping={1: "A", 2: "B"}),),
        exhausted=True,
        nodes=12,
        best_mapping={1: "A", 2: "B"},
    )
    monkeypatch.setattr(corpus_module, "english_lexicon", lambda: object())
    monkeypatch.setattr(corpus_module, "solve", lambda _puzzle, _lexicon: solved)

    summary = benchmark_solutions(
        (entry,),
        {1: {"status": "ok", "grid": [[1, 2], [".", 1]]}},
    )

    assert summary["certified"] == 1
    assert summary["unsolved"] == []
    assert summary["publisher_scored"] == 1
    assert summary["publisher_mismatches"] == []
    assert summary["outcomes"][0]["publisher_match"] is True


def test_write_audit_reports_separates_number_and_clue_queues(tmp_path: Path) -> None:
    grid_image = np.full((1500, 1500, 3), 255, dtype=np.uint8)
    cv2.putText(grid_image, "6", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    solution_image = grid_image.copy()
    cv2.putText(solution_image, "L", (25, 90), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    photo = tmp_path / "puzzle.jpg"
    solution = tmp_path / "solution.jpg"
    truth = tmp_path / "truth.toml"
    truth.write_text('format_version = 1\n[clues]\n"6" = "L"\n')
    cv2.imwrite(str(photo), grid_image)
    cv2.imwrite(str(solution), solution_image)
    work = tmp_path / "work" / "puzzle_44"
    work.mkdir(parents=True)
    cv2.imwrite(str(work / "grid.png"), grid_image)
    cv2.imwrite(str(work / "reference-grid.png"), grid_image[:200, :1300])
    cv2.imwrite(str(work / "clue-source-5.jpg"), grid_image[:100, :100])
    cv2.imwrite(str(work / "clue-5.png"), grid_image[:100, :100])
    result = {
        "status": "ok",
        "grid": [[6, "."], [".", 8]],
        "evidence": [
            {"row": 1, "column": 1, "reading": "6", "confidence": 90.0, "trusted": True},
            {"row": 2, "column": 2, "reading": "8", "confidence": 50.0, "trusted": False},
        ],
        "number_accuracy": {"mismatches": [{"row": 1, "column": 1, "reading": "6", "expected": 8, "confidence": 90.0}]},
        "clue_evidence": [
            {"symbol": 5, "reading": "S", "confidence": 33.333},
            {"symbol": 6, "reading": "O", "confidence": 90.0},
        ],
        "clue_accuracy": {"mismatches": [{"symbol": 6, "reading": "O", "expected": "Q", "confidence": 90.0}]},
    }

    target = write_audit_reports(
        entries=(CorpusEntry(puzzle_id=44, photo=photo, solution=solution, truth=truth),),
        results={44: result},
        work_root=tmp_path / "work",
        destination=tmp_path / "audit",
        review_threshold=70.0,
        number_summary={"puzzles": 0},
        clue_summary={"puzzles": 0},
    )

    assert target == (tmp_path / "audit" / "index.html").resolve()
    assert "Independent recognition concerns" in target.read_text()
    numbers = (tmp_path / "audit" / "numbers.html").read_text()
    clues = (tmp_path / "audit" / "clues.html").read_text()
    assert "r02c02" in numbers
    assert numbers.index("r01c01") < numbers.index("r02c02")
    assert "supporting evidence only" in numbers
    assert "symbol 5" in clues
    assert "33%" in clues
    assert "symbol 6" in clues
    assert clues.index("symbol 6") < clues.index("symbol 5")
    solutions = (tmp_path / "audit" / "solutions.html").read_text()
    assert "Publisher solution approval" in solutions
    assert "Prepare approved TOML" in solutions
    assert 'data-symbol="6"' in solutions
