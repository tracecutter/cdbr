"""
docs.psym.backends.readme

Render the README.md documentation artifact.

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from pathlib import Path

from psym import Backend, BackendContext, RenderJob, Template


class ReadmeBackend(Backend):
    """
    README backend.

    Produces a single README.md artifact using the shared
    documentation symbol universe.
    """

    def render_literal(self, value: str, *, lang: str | None, indent: str) -> str:
        lang = lang or ""

        lines = value.splitlines()

        out = []
        out.append("")  # ensure separation

        out.append(f"{indent}```{lang}")
        for line in lines:
            out.append(f"{indent}{line}" if line else "")
        out.append(f"{indent}```")

        out.append("")  # ensure separation

        return "\n".join(out)

    def build(self, ctx: BackendContext):
        template = Template.from_file(ctx.docs_root / "templates/readme.md.pf")

        yield RenderJob(
            template=template,
            symbols=ctx.symbols,
            output_path=Path("readme/README.md"),
            fmt="md",
            render_hooks=self,
        )


# Announcement
PSYM_BACKEND = ReadmeBackend(
    requests=["project", "fs", "dynamic", "api"],
    code=[
        Path("main.py"),
        Path("core/d2d.py"),
    ],
)
