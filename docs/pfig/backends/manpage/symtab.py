"""
docs.pfig.backends.manpage.symbols

Manpage symbol table administration

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin.
:license: PROPRIETARY, see LICENSE for details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pfig import SymbolTable, CLISpec, ArgSpec, PfigDocsBackendError
from pfig import symbol_add, symbols_code_extract

# ---------------------------------------------------------------------------
# ManpageSymtab Class
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ManpageSymtab:
    symbols: SymbolTable
    cli: Any
    command: Any  # always set (None only if you explicitly pass it)

    prog: str
    section: int
    meta: dict[str, Any]

    # ---- Root
    def root(self) -> dict:
        symtab = self.symbols.clone()

        # ---- static bindings
        _add(symtab, "dynamic.manpage.prog", self.prog, fmt="text")
        _add(symtab, "dynamic.manpage.section", self.section, fmt="text")

        # ---- dynamic root sections
        _add(symtab, "dynamic.manpage.cli.synopsis", _value_synopsis(self.cli))
        _add(symtab, "dynamic.manpage.section.options", _value_options(self.cli.options))
        _add(symtab, "dynamic.manpage.section.commands", _value_commands(self.cli.commands))
        _add(symtab, "dynamic.manpage.section.exit_status", _value_exit_status(self.prog))
        _add(symtab, "dynamic.manpage.section.see_also", _value_see_also(self.cli.commands))

        # ---- meta symbols
        for name, value in self.meta.items():
            _add(symtab, name, value)

        return symtab

    # ---- Subcommand
    def subcmd(self) -> dict:
        symtab = self.symbols.clone()

        cmd = self.command

        sub_spec = CLISpec(
            prog=f"{self.prog} {cmd.name}",
            help=cmd.help,
            tagline=cmd.tagline,
            options=cmd.options,
            args=getattr(cmd, "args", []),
            commands=[],
        )

        # ---- Subcommand dynamic symbols
        _add(symtab, "dynamic.subcmd.name", cmd.name, fmt="text")
        _add(symtab, "dynamic.subcmd.name.upper", cmd.name.upper(), fmt="text")
        _add(symtab, "dynamic.subcmd.name.title", cmd.name.title(), fmt="text")
        _add(symtab, "dynamic.subcmd.name.lower", cmd.name.lower(), fmt="text")
        _add(symtab, "dynamic.subcmd.tagline", cmd.tagline, fmt="text")

        _add(symtab, "dynamic.subcmd.synopsis", _value_synopsis(sub_spec))
        _add(symtab, "dynamic.subcmd.options", _value_options(sub_spec.options))

        # ---- Source extraction
        source_root = self.meta["source_root"]
        subcmd_path = (source_root / "cmds" / cmd.name).with_suffix(".py")

        if not subcmd_path.exists():
            raise PfigDocsBackendError(f"{cmd.name}: source file not found: {subcmd_path}")

        symbols_code_extract(symtab, [subcmd_path])

        return symtab


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add(symtab, name, value, *, fmt="nroff") -> None:
    symbol_add(symtab, name, value, origin="manpage.symtab", fmt=fmt)


def _lower_meta(meta: str | None) -> str | None:
    if not meta:
        return None
    return meta.lower()


def _synopsis_forms(opt) -> list[str]:
    """
    Return a list of flag forms to be OR'd together inside one [] group.
    Uses declaration order as much as possible.
    """

    forms: list[str] = []

    # Start with declared flags (e.g. ["-f","--file"] or ["--emoji","--no-emoji"])
    for f in opt.flags:
        if opt.metavar:
            forms.append(f"{f} {opt.metavar.lower()}")
        else:
            forms.append(f)

    # If you ever store bool secondary separately, merge it here (harmless if empty)
    for f in getattr(opt, "secondary", []) or []:
        if f not in opt.flags:
            if opt.metavar:
                forms.append(f"{f} {opt.metavar.lower()}")
            else:
                forms.append(f)

    return forms


def _synopsis_token(opt) -> str:
    forms = _synopsis_forms(opt)
    if len(forms) == 1:
        return f"[{forms[0]}]"
    return "[{}]".format(" | ".join(forms))


def _short_description(help_text: str) -> str:
    for line in help_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("Usage:"):
            continue
        return s
    return ""


def _value_synopsis(spec: CLISpec) -> str:
    """
    High-typography SSH-style synopsis renderer.

    - Bold flags
    - Italic metavars
    - Show defaults on primary long form
    - Bool-pair collapse (--no-x when default true)
    - Clean wrapping
    """

    prog = spec.prog
    width = 72
    indent = len(prog) + 1

    # ---- Build option tokens
    tokens: list[str] = []

    for opt in spec.options:
        forms: list[str] = []

        # Bool pair (--emoji / --no-emoji)
        if opt.is_bool_pair:
            if opt.default == "true":
                tok = rf"[\fB{opt.secondary[0]}\fR]"
            else:
                tok = rf"[\fB{opt.primary}\fR]"
            tokens.append(tok)
            continue

        # Simple flags (-v / --verbose)
        if opt.is_flag:
            if opt.default == "true":
                continue  # default enabled → hide

            forms.extend(rf"\fB{f}\fR" for f in opt.flags)

        # Value options
        else:
            for f in opt.flags:
                flag = rf"\fB{f}\fR"

                if opt.metavar:
                    mv = rf"\fI{opt.metavar.lower()}\fR"

                    if opt.default and f == opt.primary:
                        mv = rf"{mv}=\fI{opt.default}\fR"

                    forms.append(f"{flag} {mv}")
                else:
                    forms.append(flag)

        if not forms:
            continue

        if len(forms) > 1:
            tok = "[{}]".format(" | ".join(forms))
        else:
            tok = f"[{forms[0]}]"

        tokens.append(tok)

    # ---- Wrap tokens
    lines: list[str] = []
    line = ""

    for tok in tokens:
        if not line:
            line = tok
            continue

        if len(line) + 1 + len(tok) > width:
            lines.append(line)
            line = tok
        else:
            line += " " + tok

    if line:
        lines.append(line)

    # ---- Emit synopsis with arguments on last line if wrapping
    out: list[str] = []
    out.append(f".B {prog}")

    positional = ""
    if spec.args:
        positional = " ".join(_render_arg(a) for a in spec.args)

    # No options
    if not lines:
        if positional:
            out[-1] += " " + positional
    else:
        # Emit wrapped option lines
        for i, line in enumerate(lines):
            out.append(line if i == 0 else (" " * indent + line))

        # If options wrapped across multiple lines → args get their own line
        if positional:
            if len(lines) > 1:
                out.append(" " * indent + positional)
            else:
                # single option line → inline
                out[-1] += " " + positional

    # Root-only
    if spec.commands:
        out.append(" " * indent + "<command> [args...]")

    return "\n".join(out)


def _value_options(options) -> str:
    lines: list[str] = []

    for opt in options:
        lines.append(".TP")

        flags = ", ".join(opt.flags)

        if opt.metavar:
            mv = _lower_meta(opt.metavar)
            flags += f" \\fI{mv}\\fR"

        lines.append(".B " + flags)

        help_text = opt.help or ""

        if opt.default:
            help_text += f" (default: \\fI{opt.default}\\fR)"

        lines.append(help_text.strip())
        lines.append("")

    return "\n".join(lines)


def _render_arg(a: ArgSpec) -> str:
    token = rf"\fI{a.metavar}\fR"
    if a.nargs == -1:
        token = f"{token}..."
    if not a.required:
        token = f"[{token}]"
    return token


def _value_commands(commands) -> str:
    lines: list[str] = []

    # Tighten spacing between .TP items
    lines.append(".PD 0")

    for cmd in commands:
        lines.append(".TP")
        lines.append(".B " + cmd.name)
        lines.append(_short_description(cmd.help))

    # Restore default paragraph distance (tweak if you prefer)
    lines.append(".PD 1v")

    return "\n".join(lines)


def _value_see_also(commands) -> str:
    lines: list[str] = []

    # Generate subcommand manpage references
    refs: list[str] = []
    for cmd in commands:
        refs.append(f".BR pkit-{cmd.name} (1)")

    # Optional: external tools
    refs.extend(
        [
            ".BR pip (1)",
            ".BR pipx (1)",
            ".BR build (1)",
        ]
    )

    # Add commas except for last entry
    for i, ref in enumerate(refs):
        if i < len(refs) - 1:
            lines.append(ref + ",")
        else:
            lines.append(ref)

    return "\n".join(lines)


def _value_exit_status(prog: str) -> str:
    return f"The \\fB{prog}\\fR command exits with status 0 on success and a non-zero value if an error occurs."
