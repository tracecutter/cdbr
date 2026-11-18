"""
cdbr.tests.cmd.basic.test_cmd_basic

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from pathlib import Path
import importlib

import cv2
from click.testing import CliRunner
import numpy as np

from cdbr.test.fs import populate_fs
from cdbr.test.harness import run_cdbr

main_module = importlib.import_module("cdbr.main")


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
    result = run_cdbr(["--orig", str(photo)], cwd=tmp_path)

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


def test_create_command(monkeypatch):
    monkeypatch.setattr(main_module, "english_lexicon", object)
    monkeypatch.setattr(
        main_module,
        "generate_puzzle",
        lambda lexicon, seed, limits, progress, required_words, excluded_words: (
            seed,
            required_words,
            excluded_words,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "generated_puzzle_to_toml",
        lambda value, include_answer: (
            f"seed = {value[0]}\ntheme = {value[1][0]}\n"
            f"excluded = {value[2][0]}\nanswer = {str(include_answer).lower()}\n"
        ),
    )

    result = CliRunner().invoke(
        main_module.create_main,
        ["--seed", "23", "--include", "PERFECT", "--exclude", "NASH", "--answer"],
    )

    assert result.exit_code == 0
    assert result.stdout == "seed = 23\ntheme = PERFECT\nexcluded = NASH\nanswer = true\n\n"


def test_image_option_derives_output_name(tmp_path, monkeypatch):
    photo = tmp_path / "puzzle.HEIC"
    photo.touch()
    captured = []
    monkeypatch.setattr(main_module, "cdbr", captured.append)

    result = CliRunner().invoke(main_module.cdbr_main, ["--image", str(photo)])

    assert result.exit_code == 0
    assert captured[0].solution_image == tmp_path / "puzzle_solved.HEIC"
    assert captured[0].orig is False


def test_image_option_accepts_explicit_output_and_protects_it(tmp_path, monkeypatch):
    photo = tmp_path / "puzzle.png"
    photo.touch()
    destination = tmp_path / "answer.png"
    captured = []
    monkeypatch.setattr(main_module, "cdbr", captured.append)

    result = CliRunner().invoke(main_module.cdbr_main, [str(photo), "--image", str(destination)])

    assert result.exit_code == 0
    assert captured[0].solution_image == destination

    destination.touch()
    result = CliRunner().invoke(main_module.cdbr_main, [str(photo), f"--image={destination}"])
    assert result.exit_code == 1
    assert "use --force to overwrite" in str(result.exception)

    result = CliRunner().invoke(main_module.cdbr_main, ["--force", str(photo), "-i", str(destination)])
    assert result.exit_code == 0
