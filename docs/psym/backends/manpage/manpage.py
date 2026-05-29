"""
docs.psym.backends.manpage.manpage

Render manpage documentation artifacts.

Produces:

    man1/<invocation>.1
    man1/<invocation>-<subcmd>.1

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from pathlib import Path
from psym import Backend, BackendContext, RenderJob, Template
from .symtab import ManpageSymtab


class ManpageBackend(Backend):
    def build(self, ctx: BackendContext):
        tpl_root = Template.from_file(ctx.docs_root / "templates/manpage/manpage.nr.pf")
        tpl_sub = Template.from_file(ctx.docs_root / "templates/manpage/manpage.subcmd.nr.pf")

        base = ctx.symbols
        invocation = base.get("project.invocation").value

        runtime = ctx.ctx_docs.target.runtime
        info = ctx.ctx_docs.target.info

        cli = runtime.cli_spec
        pkg_source = info.path_pkg_source

        # ---- Root command
        root_symtab = ManpageSymtab(
            symbols=base,
            cli=cli,
            command=None,
            prog=invocation,
            section=1,
            meta={},
        ).root()

        yield RenderJob(
            template=tpl_root,
            symbols=root_symtab,
            output_path=Path(f"manpage/man1/{invocation}.1"),
            fmt="nroff",
        )

        # ---- Subcommands
        for cmd in cli.commands:
            subcmd_symtab = ManpageSymtab(
                symbols=base,
                cli=cli,
                command=cmd,
                prog=invocation,
                section=1,
                meta={
                    "source_root": pkg_source,
                },
            ).subcmd()

            yield RenderJob(
                template=tpl_sub,
                symbols=subcmd_symtab,
                output_path=Path(f"manpage/man1/{invocation}-{cmd.name}.1"),
                fmt="nroff",
            )


# Announcement
PSYM_BACKEND = ManpageBackend(
    requests=["project", "fs", "dynamic"],
    code=[
        Path("main.py"),
    ],
)
