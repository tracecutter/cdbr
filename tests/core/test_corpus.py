"""Tests for resumable local corpus benchmarking."""

from pathlib import Path

import pytest

from cdbr.corpus import load_manifest, summarize, summarize_classification


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
