"""Build compact OCR evidence banks from the human-reviewed corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

import cv2
import numpy as np

from cdbr.core.recognition import _cell_images, _reviewed_number_feature


def _reviewed_samples(
    results: Path,
    work_root: Path,
    truth_root: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
        defects = {
            (int(coordinate[1:3]), int(coordinate[4:6])): int(value)
            for coordinate, value in truth.get("number_defects", {}).items()
        }
        reviewed_grid = tuple(str(row).split() for row in truth.get("grid", ()))
        grid = cv2.imread(str(work_root / f"puzzle_{puzzle_id:02d}" / "grid.png"))
        if grid is None:
            raise ValueError(f"Missing normalised grid for puzzle {puzzle_id}")
        grid_size = len(result["grid"])
        cells = {(row + 1, column + 1): cell for row, column, cell in _cell_images(grid, grid_size)}
        for evidence in result["evidence"]:
            position = int(evidence["row"]), int(evidence["column"])
            reading = str(evidence["reading"])
            if reviewed_grid:
                token = reviewed_grid[position[0] - 1][position[1] - 1]
                value = int(token) if token != "##" else 0
            else:
                value = defects.get(position, int(reading) if reading.isdigit() else 0)
            if not 1 <= value <= 26:
                continue
            features.append(_reviewed_number_feature(cells[position]))
            labels.append(value)
            puzzle_ids.append(puzzle_id)
    return (
        np.stack(features).astype(np.uint8),
        np.asarray(labels, dtype=np.uint8),
        np.asarray(puzzle_ids, dtype=np.uint8),
    )


def build_number_ambiguities(results: Path, work_root: Path, truth_root: Path, destination: Path) -> int:
    """Build reviewed whole-token ambiguity families without retaining photographs."""

    all_features, all_labels, all_puzzle_ids = _reviewed_samples(results, work_root, truth_root)
    selected = np.isin(all_labels, (6, 8, 9, 16, 18, 19))
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        features=all_features[selected],
        labels=all_labels[selected],
        puzzle_ids=all_puzzle_ids[selected],
    )
    return int(np.count_nonzero(selected))


def build_number_tokens(
    results: Path,
    work_root: Path,
    truth_root: Path,
    destination: Path,
    *,
    prototypes_per_number: int = 12,
    profile: str = "book-15x15-v1",
) -> int:
    """Build compact whole-number prototypes, including leave-one-puzzle-out banks."""

    features, labels, puzzle_ids = _reviewed_samples(results, work_root, truth_root)
    exclusions = np.asarray((0, *sorted({int(value) for value in puzzle_ids})), dtype=np.uint8)
    banks: list[np.ndarray] = []
    prototype_labels = np.repeat(np.arange(1, 27, dtype=np.uint8), prototypes_per_number)
    for excluded in exclusions:
        bank: list[np.ndarray] = []
        cv2.setRNGSeed(42 + int(excluded))
        for value in range(1, 27):
            selected = labels == value
            if excluded:
                selected &= puzzle_ids != excluded
            samples = features[selected].reshape(-1, 600).astype(np.float32)
            if len(samples) < prototypes_per_number:
                raise ValueError(f"Not enough reviewed samples for number {value} excluding puzzle {excluded}")
            _, _, centres = cv2.kmeans(
                samples,
                prototypes_per_number,
                np.empty((0, 1), dtype=np.int32),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1),
                5,
                cv2.KMEANS_PP_CENTERS,
            )
            bank.extend(centres.reshape(prototypes_per_number, 30, 20))
        banks.append(np.clip(np.stack(bank), 0, 255).astype(np.uint8))
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        features=np.stack(banks),
        labels=prototype_labels,
        exclusions=exclusions,
        profile=np.asarray(profile),
    )
    return len(prototype_labels)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("/tmp/cdbr-corpus/results.jsonl"))
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cdbr-corpus/work"))
    parser.add_argument("--truth-root", type=Path, default=Path("solutions/truth"))
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("cdbr/assets/ocr/number-ambiguities.npz"),
    )
    parser.add_argument(
        "--token-destination",
        type=Path,
        default=Path("cdbr/assets/ocr/number-tokens.npz"),
    )
    parser.add_argument("--profile", default="book-15x15-v1")
    arguments = parser.parse_args()
    count = build_number_ambiguities(
        arguments.results,
        arguments.work_root,
        arguments.truth_root,
        arguments.destination,
    )
    print(f"wrote {count} reviewed number templates to {arguments.destination}")
    token_count = build_number_tokens(
        arguments.results,
        arguments.work_root,
        arguments.truth_root,
        arguments.token_destination,
        profile=arguments.profile,
    )
    print(f"wrote {token_count} whole-number prototypes per bank to {arguments.token_destination}")


if __name__ == "__main__":
    main()
