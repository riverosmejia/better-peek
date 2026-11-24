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
    """The active profile's home: ``hermes_constants`` knows the profile, ``HERMES_HOME`` may name the
    launch one. The env form stays for the standalone ``python3 peek_cli.py`` the widget runs."""
    try:
        from hermes_constants import get_hermes_home

        return str(get_hermes_home())
    except Exception:  # noqa: BLE001 - outside Hermes there is no profile to ask
        return os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")


# Refused outside Hermes, where agent.file_safety is not importable: the same class of file the
# core's read guard refuses, matched by name.
_FALLBACK_SECRET_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production", ".env.test", ".env.staging",
    ".envrc", ".netrc", "_netrc", ".npmrc", ".pypirc", ".pgpass", ".git-credentials",
    "auth.json", ".anthropic_oauth.json", "webhook_subscriptions.json", "hosts.yml",
}
_FALLBACK_SECRET_DIRS = (
    os.path.join(".ssh"), os.path.join(".aws"), os.path.join(".gnupg"), os.path.join(".kube"),
    os.path.join(".docker"), os.path.join(".azure"), os.path.join(".config", "gh"),
    os.path.join(".config", "gcloud"), "mcp-tokens", "vault", "browser-profile", "webapp",
)


def secret_refusal(path: str) -> str | None:
    """Why ``path`` must not be opened, or None.

    A preview is bytes leaving Hermes — on a gateway they reach a chat — so it obeys the
    same denylist the file tools do, plus the home credential stores (the reviewer's list). Realpath,
    so a symlink with an innocuous name does not get around it.
    """
    try:
        from agent.file_safety import get_read_block_error, resolved_home_credential_stores
    except Exception:  # noqa: BLE001 - standalone: no Hermes to ask
        real = os.path.realpath(path)
        name = os.path.basename(real).casefold()
        if name in _FALLBACK_SECRET_NAMES or name.startswith(".env.") or name.startswith(".env"):
            return f"{path} is a secret-bearing file, and /peek does not read it."
        home = os.path.realpath(os.path.expanduser("~"))
        for part in _FALLBACK_SECRET_DIRS:
            store = os.path.join(home, part)
            if real == store or real.startswith(store + os.sep):
                return f"{path} is a credential store, and /peek does not read it."
        return None
    error = get_read_block_error(path)
    if error:
        return f"{path} is a secret-bearing or credential file, and /peek does not read it."
    real = os.path.realpath(path)
    files, dirs = resolved_home_credential_stores()
    if real in files or any(real == store or real.startswith(store + os.sep) for store in dirs):
        return f"{path} is a credential store, and /peek does not read it."
    return None


def redacted(text: str) -> str:
    """Every excerpt leaves through here: a plugin's output must never carry a raw secret."""
    try:
        from agent.redact import redact_sensitive_text

        return redact_sensitive_text(text, force=True)
    except Exception:  # noqa: BLE001 - standalone: nothing to redact with, and nothing to trust
        return text


def last_message(session_id: str | None = None) -> tuple[str, str | None]:
    """The last assistant message and the folder its session ran in, or ("", None).

    Only this session's: with no ``session_id`` (a fresh gateway chat) the answer is nothing, never
    the newest message of every session — that is another user's chat.
    """
    if not session_id:
        return "", None
    path = os.path.join(hermes_home(), "state.db")
    if not os.path.exists(path):
        return "", None
    query = (
        "select m.content, s.cwd from messages m join sessions s on s.id = m.session_id"
        " where m.role = 'assistant' and length(coalesce(m.content, '')) > 0"
        " and m.session_id = ? order by m.timestamp desc limit 1"
    )
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = db.execute(query, (session_id,)).fetchone()
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
        where = f":{hit.line}" if hit.line else ""
        if secret_refusal(hit.path):
            lines.append(f"{str(i).rjust(width)}  {hit.label}{where}  (hidden: credential)")
            continue
        try:
            stat = os.stat(hit.path)
            kind = "dir" if os.path.isdir(hit.path) else size_of(stat.st_size)
            when = ago(stat.st_mtime)
        except OSError:
            kind, when = "?", "?"
        lines.append(f"{str(i).rjust(width)}  {hit.label}{where}  ({kind}, {when})")
    return redacted("\n".join(lines))


def card(hit: Hit, rows: int = ROWS) -> str:
    """One path, redacted at the exit: no caller of this can return a raw secret."""
    return redacted(_card(hit, rows))


def _card(hit: Hit, rows: int = ROWS) -> str:
    """One path: what it is, and its lines numbered, the one the path names marked."""
    try:
        stat = os.stat(hit.path)
    except OSError:
        return f"{hit.path}\nnot there"
    refused = secret_refusal(hit.path)
    if refused:
        return refused
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
