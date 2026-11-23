"""
docs.psym.backends.manpage.manpage

Render manpage documentation artifacts.

Produces:

    man1/<invocation>.1

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from pathlib import Path
from psym import Backend, BackendContext, RenderJob, Template
from psym.core import usage
from .symtab import ManpageSymtab


class ManpageBackend(Backend):
    def build(self, ctx: BackendContext):
        tpl = Template.from_file(ctx.docs_root / "templates/manpage/manpage.nr.pf")
        daemon_tpl = Template.from_file(ctx.docs_root / "templates/manpage/cdbrd.nr.pf")

        base = ctx.symbols
        invocation = base.get("project.invocation").value

        cli = ctx.ctx_docs.target.runtime.cli_spec

        symtab = ManpageSymtab(
            symbols=base,
            cli=cli,
            prog=invocation,
            section=1,
            meta={},
        ).root()

        yield RenderJob(
            template=tpl,
            symbols=symtab,
            output_path=Path(f"manpage/man1/{invocation}.1"),
            fmt="nroff",
        )

        daemon = usage.from_click("cdbrd", ctx.ctx_docs.target.info.path_pyproject)
        if daemon is None:
            raise ValueError("Could not derive the cdbrd command specification")
        daemon_symtab = ManpageSymtab(
            symbols=base,
            cli=daemon,
            prog="cdbrd",
            section=1,
            meta={},
        ).root()
        yield RenderJob(
            template=daemon_tpl,
            symbols=daemon_symtab,
            output_path=Path("manpage/man1/cdbrd.1"),
            fmt="nroff",
        )


# Announcement
PSYM_BACKEND = ManpageBackend(
    requests=["project", "fs", "dynamic"],
    code=[
        Path("main.py"),
        Path("server.py"),
    ],
)
