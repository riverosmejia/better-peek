"""better-peek: the paths an answer names, and a glimpse of what is in them.

    /peek            the paths of the last answer, numbered, with size and age
    /peek 2          that one, its lines numbered, the one it names marked
    /peek src/app.ts:42

The port of midudev's quick-peek (MIT) to a shell that has no pointer: the hover
becomes a command. The logic lives in peek_paths / peek_code / peek_cli next door; this file is
only the plugin seam.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import peek_cli  # noqa: E402  (sibling module, not a package import: the loader decides the name)


def register(ctx) -> None:
    ctx.register_command(
        "peek",
        _peek,
        description="Preview the paths of the last answer (a number from the list, or path[:line])",
        args_hint="[path[:line]|n]",
    )


def _peek(raw_args: str = "", **context) -> str:
    """The answer a slash command prints. Never raises: a broken preview must not eat the session."""
    try:
        return _answer((raw_args or "").strip(), context.get("session_id") or None)
    except Exception:  # noqa: BLE001 - a plugin command reports, it does not crash the turn
        return "peek failed:\n" + traceback.format_exc(limit=2)


def _answer(arg: str, session_id: str | None) -> str:
    text, cwd = peek_cli.last_message(session_id)
    base = cwd or os.getcwd()
    home = os.path.expanduser("~")

    if not arg:
        if not text:
            return "no answer recorded yet in this session: /peek <path>"
        return peek_cli.listing(peek_cli.candidates(text, base, None, home))

    if arg.isdigit():
        hits = peek_cli.candidates(text, base, None, home) if text else []
        if not 1 <= int(arg) <= len(hits):
            return f"no path #{arg}: /peek lists them"
        return peek_cli.card(hits[int(arg) - 1])

    found = peek_cli.candidates(arg, base, None, home, limit=1)
    if not found:
        return f"nothing to peek at: {arg}"
    return peek_cli.card(found[0])
