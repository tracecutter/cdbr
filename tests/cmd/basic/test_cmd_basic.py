"""
cdbr.tests.cmd.basic.test_cmd_basic

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from pathlib import Path

from cdbr.test.fs import populate_fs
from cdbr.test.harness import run_cdbr


def test_cmd_basic(tmp_path):
    here = Path(__file__).parent

    # Arrange: copy test filesystem (if needed)
    populate_fs(here / "before", tmp_path)

    # Act: run cdbr with a couple of options
    result = run_cdbr(
        [
            "--dry-run",
            "--name",
            "alice",
            "--pattern",
            "foo",
            "--output",
            "out.txt",
        ],
        cwd=tmp_path,
    )

    # Assert: command succeeds
    assert result.exitcode == 0

    # Assert: basic output sanity (worker ran)
    assert "cdbr invocation" in result.stderr
    assert "alice" in result.stderr
    assert "foo" in result.stderr
