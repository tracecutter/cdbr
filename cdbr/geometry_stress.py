"""Measure puzzle-grid recovery against deterministic photo distortions."""

import csv
import sys
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

import cdbr.ui as click
from cdbr.core.recognition import (
    _block_mask,
    _cell_images,
    _orient_photo_grid,
    detect_grid_size,
    normalize_grid_lattice,
    normalize_photo,
)


def distort(image: np.ndarray, rotation: float, skew: float, curl: float, scale: float) -> np.ndarray:
    height, width = image.shape[:2]
    corners = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    target = corners.copy()
    # Pull the top corners inward and tilt the top edge.
    target[0] += (skew * width, skew * height)
    target[1] += (-skew * width, 0)
    perspective = cv2.getPerspectiveTransform(corners, target)
    affine = cv2.getRotationMatrix2D((width / 2, height / 2), rotation, scale)
    transform = np.vstack((affine, [0, 0, 1])) @ perspective
    background = (245, 245, 245)
    warped = cv2.warpPerspective(image, transform, (width, height), borderValue=background)
    if not curl:
        return warped
    # A smooth vertical bow simulates curved rule lines on a bent page.
    x, y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    bow = curl * height * np.sin(np.pi * x / (width - 1))
    return cv2.remap(warped, x, y - bow, cv2.INTER_LINEAR, borderValue=background)


def grid_layout(image: np.ndarray) -> tuple[int, list[bool]]:
    _, grid = _orient_photo_grid(image)
    size = detect_grid_size(grid)
    return size, _block_mask(_cell_images(normalize_grid_lattice(grid, size), size), size)


def adjust_lighting(image: np.ndarray, exposure: float, shadow: float) -> np.ndarray:
    """Apply an exposure multiplier and a soft shadow from the left edge."""

    x = np.linspace(0, 1, image.shape[1], dtype=np.float32)
    transmission = 1 - shadow * (1 - np.tanh((x - 0.45) / 0.10)) / 2
    return np.clip(image * (exposure * transmission[None, :, None]), 0, 255).astype(np.uint8)


@click.command()
@click.argument("photo", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--quick", is_flag=True, help="Run a subset covering neutral, individual and combined stresses.")
@click.option("--lighting", is_flag=True, help="Run 25 exposure/shadow combinations on the original geometry.")
def main(photo: Path, quick: bool, lighting: bool) -> None:
    """Write per-case geometry results as CSV. Progress and totals go to stderr."""

    with TemporaryDirectory(prefix="cdbr-geometry-") as directory:
        normalized = Path(directory) / "photo.png"
        normalize_photo(photo, normalized)
        image = cv2.imread(str(normalized))
    if image is None:
        raise click.ClickException(f"Could not decode {photo}")
    try:
        expected_size, expected_layout = grid_layout(image)
    except ValueError as exc:
        raise click.ClickException(f"Baseline grid failed: {exc}") from exc

    axes = (
        (-10, -5, 0, 5, 10),
        (0, 0.04, 0.08, 0.12, 0.16),
        (-0.04, -0.02, 0, 0.02, 0.04),
        (0.60, 0.70, 0.80, 0.90, 1.0),
    )
    if quick and lighting:
        raise click.UsageError("Choose either --quick or --lighting.")
    if quick:
        cases: list[tuple[float, float, float, float]] = [
            (0, 0, 0, 1),
            (-10, 0, 0, 1),
            (10, 0, 0, 1),
            (0, 0.16, 0, 1),
            (0, 0, -0.04, 1),
            (0, 0, 0.04, 1),
            (0, 0, 0, 0.60),
        ]
        cases.extend((angle, 0.12, curl, 0.70) for angle, curl in product((-10, 10), (-0.04, 0.04)))
    else:
        cases = list(product(axes[0], axes[1], axes[2], axes[3]))
    if lighting:
        conditions: list[tuple[float, float, float, float, float, float]] = [
            (0, 0, 0, 1, exposure, shadow)
            for exposure, shadow in product((0.45, 0.70, 1.0, 1.25, 1.50), (0, 0.15, 0.30, 0.45, 0.60))
        ]
    else:
        conditions = [(*case, 1.0, 0.0) for case in cases]
    writer = csv.writer(sys.stdout)
    writer.writerow(
        ("rotation_deg", "skew", "curl", "scale", "status", "grid_size", "block_errors", "detail", "exposure", "shadow")
    )
    exact = 0
    for index, (angle, skew, curl, scale, exposure, shadow) in enumerate(conditions, 1):
        case = (angle, skew, curl, scale)
        light = (exposure, shadow)
        transformed = adjust_lighting(image, *light) if lighting else distort(image, *case)
        try:
            size, layout = grid_layout(transformed)
        except ValueError as exc:
            writer.writerow((*case, "detection_failed", "", "", str(exc), *light))
        else:
            if size != expected_size:
                writer.writerow((*case, "wrong_size", size, "", "", *light))
            else:
                errors = sum(a != b for a, b in zip(layout, expected_layout, strict=True))
                exact += errors == 0
                writer.writerow((*case, "exact" if errors == 0 else "block_mismatch", size, errors, "", *light))
        if index % 25 == 0:
            sys.stdout.flush()
            click.echo(f"{index}/{len(conditions)} cases complete", err=True)
    click.echo(f"Exact block layout: {exact}/{len(conditions)}", err=True)


if __name__ == "__main__":
    main()
