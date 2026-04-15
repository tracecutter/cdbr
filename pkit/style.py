"""
pkit.style

pkit stylistic choices

This module exports styley freaky to avoid look and feel leaky.

INTERNAL

:copyright: Copyright (c) 2026 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""


class Style:
    def __init__(self):
        self.emoji = {
            "error": "❌ ",
            "warn": "⚠️  ",
            "info": "ℹ️  ",
            "section": "\n▶ ",
        }

        # ANSI
        self.RESET = "\x1b[0m"

        self.FG_WHITE = "\x1b[97m"
        self.FG_BLACK = "\x1b[30m"
        self.FG_DEFAULT = "\x1b[39m"

        self.BG_RED = "\x1b[41m"
        self.BG_GREEN = "\x1b[42m"
        self.BG_FOLD = "\x1b[47m"

        self.ELLIPSIS = " [ … ] "
        self.FOLD_LABEL = "<---- folded ---->"

    def paint(self, text: str, fg: str = "", bg: str = "") -> str:
        return f"{bg}{fg}{text}{self.RESET}"


style = Style()
