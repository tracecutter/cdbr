"""
cdbr.tests.cmd.basic.test_cmd_basic

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from pathlib import Path

import cv2
import numpy as np

from cdbr.test.fs import populate_fs
from cdbr.test.harness import run_cdbr


def test_cmd_basic(tmp_path):
    here = Path(__file__).parent

    # Arrange: copy test filesystem (if needed)
    populate_fs(here / "before", tmp_path)

    photo = tmp_path / "puzzle.png"
    image = np.full((2000, 2000, 3), 240, dtype=np.uint8)
    origin = 250
    cell_size = 100
    for row in range(15):
        for column in range(15):
            top_left = (origin + column * cell_size, origin + row * cell_size)
            bottom_right = (top_left[0] + cell_size, top_left[1] + cell_size)
            if (row + column) % 3 == 0:
                cv2.rectangle(image, top_left, bottom_right, (90, 90, 90), -1)
            else:
                value = (row * 15 + column) % 26 + 1
                cv2.putText(
                    image,
                    str(value),
                    (top_left[0] + 10, top_left[1] + 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (20, 20, 20),
                    2,
                )
            cv2.rectangle(image, top_left, bottom_right, (20, 20, 20), 3)
    cv2.imwrite(str(photo), image)

    # Act: run cdbr with a puzzle photograph.
    result = run_cdbr([str(photo)], cwd=tmp_path)

    # Assert: command succeeds
    assert result.exitcode == 0

    # Assert: basic output sanity (worker ran)
    assert 'format_version = 1' in result.stdout
    assert 'image_format = "PNG"' in result.stdout


def test_cmd_rejects_unknown_file_format(tmp_path):
    photo = tmp_path / "not-a-photo.png"
    photo.write_text("not image data")

    result = run_cdbr([str(photo)], cwd=tmp_path)

    assert result.exitcode == 2
    assert "Unsupported or unrecognised image format" in result.stderr
