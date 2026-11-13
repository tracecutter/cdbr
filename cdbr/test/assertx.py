"""
cdbr.test.assertx

An assertion framework


:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from pathlib import Path


def assert_files_equal(a: Path, b: Path) -> None:
    assert a.read_text() == b.read_text()


def assert_exitcode(result, expected: int) -> None:
    assert result.exitcode == expected
