"""The headless half of /peek: what the last message names, and the card a path gets.

Two surfaces call this: the plugin's slash command (text, printed where Hermes prints a command's
answer) and the TUI widget (--machine json). No ANSI unless the caller is a terminal.
Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

from peek_code import excerpt_of, language_of
from peek_paths import Hit, candidates

CODE_BYTES = 1024 * 1024
ROWS = 20


def hermes_home() -> str:
    return os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")


def last_message(session_id: str | None = None) -> tuple[str, str | None]:
    """The last assistant message and the folder its session ran in, or ("", None)."""
    path = os.path.join(hermes_home(), "state.db")
    if not os.path.exists(path):
        return "", None
    query = (
        "select m.content, s.cwd from messages m join sessions s on s.id = m.session_id"
        " where m.role = 'assistant' and length(coalesce(m.content, '')) > 0"
    )
    args: tuple[str, ...] = ()
    if session_id:
        query += " and m.session_id = ?"
        args = (session_id,)
    query += " order by m.timestamp desc limit 1"
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = db.execute(query, args).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return "", None
    return (row[0] or "", row[1]) if row else ("", None)


def size_of(bytes_: int) -> str:
    value = float(bytes_)
    for unit in ("B", "k", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.0f}G"


def ago(self_mtime: float) -> str:
    seconds = max(0, dt.datetime.now().timestamp() - self_mtime)
    for bound, div, unit in ((60, 1, "s"), (3600, 60, "m"), (86400, 3600, "h")):
        if seconds < bound:
            return f"{int(seconds / div)}{unit}"
    return f"{int(seconds / 86400)}d"


def listing(hits: list[Hit]) -> str:
    """The paths, numbered, each with its size or entry count, its age and the line it names."""
    if not hits:
        return "no paths in the last message"
    width = len(str(len(hits)))
    lines = []
    for i, hit in enumerate(hits, 1):
        try:
            stat = os.stat(hit.path)
            kind = "dir" if os.path.isdir(hit.path) else size_of(stat.st_size)
            when = ago(stat.st_mtime)
        except OSError:
            kind, when = "?", "?"
        where = f":{hit.line}" if hit.line else ""
        lines.append(f"{str(i).rjust(width)}  {hit.label}{where}  ({kind}, {when})")
    return "\n".join(lines)


def card(hit: Hit, rows: int = ROWS) -> str:
    """One path: what it is, and its lines numbered, the one the path names marked."""
    try:
        stat = os.stat(hit.path)
    except OSError:
        return f"{hit.path}\nnot there"
    if os.path.isdir(hit.path):
        try:
            entries = sorted(name for name in os.listdir(hit.path) if name not in ("__pycache__", ".git"))
        except OSError:
            entries = []
        body = "\n".join(f"  {name}" for name in entries[:rows]) or "  (empty)"
        return f"{os.path.basename(hit.path) or hit.path}/  dir, {min(len(entries), rows)} shown\n{body}"

    head = f"{os.path.basename(hit.path)}  {size_of(stat.st_size)}, {ago(stat.st_mtime)}"
    language = language_of(hit.path)
    if language is None or stat.st_size > CODE_BYTES:
        return f"{head}\n{hit.path}\n(no preview: {'not code or text' if language is None else 'too large'})"
    try:
        with open(hit.path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        return f"{head}\n{hit.path}\n(no preview: {exc.strerror})"
    excerpt = excerpt_of(text, language, hit.line, rows)
    if excerpt is None:
        return f"{head}\n{hit.path}\n(no preview)"
    numbered = []
    for offset, line in enumerate(excerpt.source.split("\n")):
        number = excerpt.first + offset
        mark = "▸" if number == excerpt.mark else " "
        numbered.append(f"{mark}{str(number).rjust(4)}  {line}")
    return f"{head}  ·  {excerpt.language}, {excerpt.count} lines\n" + "\n".join(numbered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="peek", description="Paths of the last message, and a preview")
    parser.add_argument("target", nargs="?", help="a number from the list, or a path[:line]")
    parser.add_argument("--session", default=None, help="session id (default: the newest)")
    parser.add_argument("--machine", choices=("json", "text"), default="text")
    parser.add_argument("--rows", type=int, default=ROWS)
    args = parser.parse_args(argv)

    text, cwd = last_message(args.session)
    hits = candidates(text, cwd or os.getcwd(), None, os.path.expanduser("~")) if text else []

    if args.target:
        hit = None
        if args.target.isdigit() and 1 <= int(args.target) <= len(hits):
            hit = hits[int(args.target) - 1]
        else:
            found = candidates(args.target, cwd or os.getcwd(), None, os.path.expanduser("~"), limit=1)
            hit = found[0] if found else None
        if hit is None:
            print("nothing to peek at: " + args.target)
            return 1
        print(card(hit, args.rows))
        return 0

    if args.machine == "json":
        print(json.dumps([{"label": h.label, "path": h.path, "line": h.line} for h in hits]))
        return 0
    print(listing(hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
