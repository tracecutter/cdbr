"""
cdbr.test.harnass

The test framework harnass


:copyright: Copyright (c) 2025 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


@dataclass
class RunResult:
    exitcode: int
    stdout: str
    stderr: str


def run_cdbr(
    args: list[str],
    cwd: Path,
    env: dict | None = None,
) -> RunResult:
    executable = Path(sys.executable).with_name("cdbr")
    proc = subprocess.run(
        [executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    return RunResult(
        exitcode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
