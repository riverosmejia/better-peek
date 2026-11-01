"""Finding the paths a text names, and where they land.

Port of plugins/quick-peek/hooks/paths.ts from midudev's quick-peek (MIT):
absolute (/a/b), from home (~/a), relative (./a, src/a.ts, README.md), each with an optional
:line or :line:column after it. A path is only a candidate here; `candidates()` keeps the ones
that lead to a file or a folder.

The rules are the original's, unchanged, so the original's tests are the contract. Stdlib only:
this has to run the same on Arch, Fedora and Ubuntu.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Found:
    """A path a text names: where it sits in the text, and the path itself, `:line` cut."""

    start: int
    end: int
    target: str


@dataclass(frozen=True)
class Hit:
    """A path that leads somewhere: as written, resolved, and the line it names."""

    label: str
    path: str
    line: int | None = None


# What a sentence puts after a path, and a line (and column) after a file.
_TRAILING = re.compile(r"""[.,;:!?)\]}>'"»”’]+$""")
_LINE = re.compile(r":\d+(?::\d+)?$")
# An address: never a path, nor the paths inside it.
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s<>()]+", re.I)
# Absolute, from home or explicitly relative; a relative path with a folder in it; a file name
# with an extension. None starts inside a word, an address or another path.
_SOURCES = (
    r"""(?:~|\.{1,2})?/[^\s`'"<>()[\]{}|*]+""",
    r"""[A-Za-z]:\\[^\s`'"<>()[\]{}|*]+""",
    r"""[\w@+-][\w@.+-]*(?:/[\w@.+-]+)+/?""",
    r"""[\w@+-][\w@.+-]*\.[A-Za-z][A-Za-z0-9]{0,9}""",
)
_CANDIDATE = re.compile(
    "|".join(r"(?<![\w/.~:\\@-])(?:%s)(?::\d+(?::\d+)?)?" % source for source in _SOURCES)
)
# A whole inline code span that is a path: it may hold spaces when it starts as a path does.
_SPAN = re.compile(r"""^(?:(?:~|\.{1,2})?/|[A-Za-z]:\\)[^\n`]*[^\s`]$""")
_CODE_SPAN = re.compile(r"`([^\n`]+)`")


def line_of(text: str) -> int | None:
    """The line a path's text names after it (`src/x.ts:12`, `src/x.ts:12:5`), if it names one."""
    line = _LINE.search(_TRAILING.sub("", text.strip()))
    return None if line is None else int(line.group(0)[1:].split(":")[0])


def _clean(text: str) -> str | None:
    """The path `text` names, with what a sentence or a line number adds after it cut."""
    target = _TRAILING.sub("", text)
    target = _LINE.sub("", target)
    target = _TRAILING.sub("", target)
    if not re.search(r"[\w~]", target) or target == "~":
        return None
    return target


def paths_in(text: str) -> list[Found]:
    """The paths named in plain text, in order."""
    masked = _URL.sub(lambda match: " " * len(match.group(0)), text)
    found: list[Found] = []
    for match in _CANDIDATE.finditer(masked):
        whole = match.group(0)
        trimmed = _TRAILING.sub("", whole)
        target = _clean(whole)
        if target is None:
            continue
        found.append(Found(match.start(), match.start() + len(trimmed), target))
    return found


def path_of_span(code: str) -> str | None:
    """The path an inline code span holds whole (`~/a b/c.mp4` or `src/x.ts:12`), if it holds one."""
    text = code.strip()
    if _SPAN.match(text):
        return _LINE.sub("", text)
    found = paths_in(text)
    if len(found) == 1 and found[0].start == 0 and found[0].end == len(text):
        return found[0].target
    return None


def resolve(target: str, cwd: str, home: str | None) -> str | None:
    """Where `target` lands: home for `~`, the working folder for a relative path; `.` and `..`
    folded, no trailing `/`. A Windows path stays as written."""
    if re.match(r"^[A-Za-z]:\\", target):
        return target
    path = target
    if path == "~" or path.startswith("~/"):
        if not home:
            return None
        path = home + path[1:]
    elif not path.startswith("/"):
        path = f"{cwd}/{path}"
    parts: list[str] = []
    for part in path.split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/" + "/".join(parts)


def candidates(
    text: str,
    cwd: str,
    root: str | None = None,
    home: str | None = None,
    limit: int = 10,
) -> list[Hit]:
    """The paths of `text` that lead to a file or a folder, deduplicated, in the order they appear.

    A relative path leads from the folder the shell is in, or else from the project's: the agent
    names paths from the project even after a `cd` took the shell into one of its folders.
    """
    home = home if home is not None else os.path.expanduser("~")
    bases = [cwd] + ([root] if root and root != cwd else [])

    named: list[tuple[int, str, int | None]] = []  # position, label, line
    for span in _CODE_SPAN.finditer(text):
        target = path_of_span(span.group(1))
        if target is not None:
            named.append((span.start(), span.group(1), line_of(span.group(1))))
    for found in paths_in(text):
        named.append((found.start, found.target, line_of(text[found.start : found.end])))
    named.sort(key=lambda item: item[0])

    hits: list[Hit] = []
    seen: set[str] = set()
    for _, label, line in named:
        for base in bases:
            path = resolve(label, base, home)
            if path is None or path in seen or not os.path.exists(path):
                continue
            seen.add(path)
            hits.append(Hit(label, path, line))
            break
        if len(hits) >= limit:
            break
    return hits
