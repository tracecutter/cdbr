"""
pkit.tests.cmd.basic.test_cmd_basic

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from pathlib import Path

from pkit.test.fs import populate_fs
from pkit.test.harness import run_pkit


def test_cmd_basic(tmp_path):
    here = Path(__file__).parent

    # Arrange: copy test filesystem (if needed)
    populate_fs(here / "before", tmp_path)

    # Act: run pkit with a couple of options
    result = run_pkit(
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
    assert "pkit invocation" in result.stderr
    assert "alice" in result.stderr
    assert "foo" in result.stderr
