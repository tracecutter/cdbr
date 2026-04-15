"""
docs.pfig.backends.sphinx

Render the Sphinx documentation set.

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from pathlib import Path

from pfig import Backend, BackendContext, RenderJob, Template
from pfig import symbol_add


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class SphinxBackend(Backend):
    # ------------------------------------------------------------------
    # discovery
    # ------------------------------------------------------------------
    def _discover_sections(self, docs_root: Path) -> list[str]:
        """
        Discover section directories under templates/sphinx.

        Returns list of section names (including 'index').
        """
        base = docs_root / "templates/sphinx"

        sections: list[str] = []

        # root index
        if (base / "index.rst.pf").exists():
            sections.append("index")

        # sub-sections (directories with index.rst.pf)
        for p in sorted(base.iterdir()):
            if not p.is_dir():
                continue
            if (p / "index.rst.pf").exists():
                sections.append(p.name)

        return sections

    def _build_toctree(self, sections: list[str]) -> str:
        """
        Build Sphinx toctree entries from discovered sections.
        """
        lines: list[str] = []

        for name in sections:
            if name == "index":
                continue
            lines.append(f"   {name}/index")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # rendering helpers
    # ------------------------------------------------------------------

    def render_literal(self, value: str, *, lang: str | None, indent: str) -> str:
        lang = lang or "text"

        lines = value.splitlines()

        out = []
        out.append("")
        out.append(f"{indent}.. code-block:: {lang}")
        out.append("")

        for line in lines:
            if line:
                out.append(f"{indent}   {line}")
            else:
                out.append("")

        out.append("")
        return "\n".join(out)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------

    def build(self, ctx: BackendContext):
        sections = self._discover_sections(ctx.docs_root)

        # ---- backend-owned symbol
        symbol_add(ctx.symbols, "dynamic.toctree", self._build_toctree(sections), origin="sphinx", fmt="rst")

        # ---- render each section
        base = ctx.docs_root / "templates/sphinx"

        for name in sections:

            if name == "index":
                template_path = base / "index.rst.pf"
                output_path = Path("sphinx/index.rst")
            else:
                template_path = base / name / "index.rst.pf"
                output_path = Path(f"sphinx/{name}/index.rst")

            template = Template.from_file(template_path)

            yield RenderJob(
                template=template,
                symbols=ctx.symbols.clone(),
                output_path=output_path,
                fmt="rst",
                render_hooks=self,
            )


# ---------------------------------------------------------------------------
# Announcement
# ---------------------------------------------------------------------------

PFIG_BACKEND = SphinxBackend(
    requests=["project", "fs", "dynamic", "api"],
    code=[
        Path("main.py"),
    ],
)
