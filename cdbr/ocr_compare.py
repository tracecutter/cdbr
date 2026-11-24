"""Compare two isolated OCR corpus benchmark summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(source: Path) -> dict[str, Any]:
    return json.loads(source.read_text(encoding="utf-8"))


def _metrics(summary: dict[str, Any]) -> dict[str, int | float | str]:
    numbers = summary["number_ocr"]
    classification = summary["classification"]
    resources = summary["resources"]
    return {
        "pipeline": summary["ocr_pipeline"],
        "accuracy_percent": numbers["accuracy_percent"],
        "incorrect": numbers["incorrect"],
        "trusted_incorrect": numbers["trusted_incorrect"],
        "mean_seconds": summary["mean_seconds"],
        "cells_per_second": classification["cells_per_second"],
        "review_cells": summary["review_cells"],
        "main_peak_rss_mb": resources["main_peak_rss_mb"],
        "child_peak_rss_mb": resources["child_peak_rss_mb"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy", type=Path)
    parser.add_argument("whole_token", type=Path)
    arguments = parser.parse_args()
    comparison = {
        "legacy": _metrics(_load(arguments.legacy)),
        "whole_token": _metrics(_load(arguments.whole_token)),
    }
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
