"""Build compact OCR evidence banks from the human-reviewed corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

import cv2
import numpy as np

from cdbr.core.recognition import _cell_images, _reviewed_number_feature


def build_number_ambiguities(results: Path, work_root: Path, truth_root: Path, destination: Path) -> int:
    """Build the 6/8 and 16/18 bank without copying full photographs."""

    features: list[np.ndarray] = []
    labels: list[int] = []
    puzzle_ids: list[int] = []
    for line in results.read_text(encoding="utf-8").splitlines():
        result = json.loads(line)
        if result.get("status") != "ok":
            continue
        puzzle_id = int(result["puzzle_id"])
        truth_path = truth_root / f"puzzle_{puzzle_id:02d}.toml"
        if not truth_path.is_file():
            continue
        with truth_path.open("rb") as stream:
            truth = tomllib.load(stream)
        if not truth.get("accept_observed_numbers", False):
            continue
        defects = {
            (int(coordinate[1:3]), int(coordinate[4:6])): int(value)
            for coordinate, value in truth.get("number_defects", {}).items()
        }
        grid = cv2.imread(str(work_root / f"puzzle_{puzzle_id:02d}" / "grid.png"))
        if grid is None:
            raise ValueError(f"Missing normalised grid for puzzle {puzzle_id}")
        grid_size = len(result["grid"])
        cells = {(row + 1, column + 1): cell for row, column, cell in _cell_images(grid, grid_size)}
        for evidence in result["evidence"]:
            position = int(evidence["row"]), int(evidence["column"])
            reading = str(evidence["reading"])
            value = defects.get(position, int(reading) if reading.isdigit() else 0)
            if value not in (6, 8, 16, 18):
                continue
            features.append(_reviewed_number_feature(cells[position]))
            labels.append(value)
            puzzle_ids.append(puzzle_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        features=np.stack(features).astype(np.uint8),
        labels=np.asarray(labels, dtype=np.uint8),
        puzzle_ids=np.asarray(puzzle_ids, dtype=np.uint8),
    )
    return len(labels)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("/tmp/cdbr-corpus/results.jsonl"))
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cdbr-corpus/work"))
    parser.add_argument("--truth-root", type=Path, default=Path("examples/truth"))
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("cdbr/assets/ocr/number-ambiguities.npz"),
    )
    arguments = parser.parse_args()
    count = build_number_ambiguities(
        arguments.results,
        arguments.work_root,
        arguments.truth_root,
        arguments.destination,
    )
    print(f"wrote {count} reviewed number templates to {arguments.destination}")


if __name__ == "__main__":
    main()
