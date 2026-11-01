"""Previewing a file of code or text: which files are, by their name; the lines a preview shows
(the first ones, or those around the line a path names); and their tokens, coloured by kind.

Port of plugins/quick-peek/hooks/code.ts from midudev's quick-peek (MIT), trimmed to the
languages we actually read here. Adding another one is copying its rule list from the original.
Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The most lines shown before the one a path names (a third of the rows, at most), a tab's
# columns, and the longest line kept.
CONTEXT = 3
TAB = "  "
LINE_CHARS = 240

# A token's kind, the colour it takes: keyword or tag, string, number, comment, type,
# attribute or key, function; plain.
Kind = str  # 'k' | 's' | 'n' | 'c' | 't' | 'a' | 'f' | ''


@dataclass(frozen=True)
class Language:
    name: str
    pattern: re.Pattern[str] | None
    kinds: tuple[Kind, ...]


@dataclass(frozen=True)
class Excerpt:
    language: str
    count: int
    first: int
    mark: int
    source: str
    lines: list[list[tuple[Kind, str]]]


def _grammar(name: str, rules: list[tuple[Kind, str]], flags: int = 0) -> Language:
    """A grammar from its rules, tried in order where two start at the same place.

    A rule must not hold a capturing group: the kind of a match is read off WHICH group matched.
    """
    for _, source in rules:
        if re.search(r"(?<!\\)\(", source) and not re.search(r"(?<!\\)\((?:\?|<\\)", source):
            raise ValueError(f"{name}: rule with a capturing group: {source}")
    pattern = re.compile("|".join(f"({source})" for _, source in rules), re.MULTILINE | flags) if rules else None
    return Language(name, pattern, tuple(kind for kind, _ in rules))


def _words(words: str) -> str:
    return r"\b(?:" + "|".join(words.split()) + r")\b"


def _block(open_: str, close: str) -> str:
    return f"{open_}[\\s\\S]*?(?:{close}|(?![\\s\\S]))"


_DQ = r'"(?:[^"\\\n]|\\.)*"?'
_SQ = r"'(?:[^'\\\n]|\\.)*'?"
_BT = r"`(?:[^`\\]|\\[\s\S])*`?"
_TRIPLE = r'"""[^"]*?(?:"""|(?![\s\S]))|\'\'\'[\s\S]*?(?:\'\'\'|(?![\s\S]))'
_NUMBER = r"\b(?:0[xX][\da-fA-F_]+|0[bB][01_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)n?\b"
_TYPE = r"\b[A-Z][A-Za-z0-9_]*\b"
_CALL = r"\b[A-Za-z_$][\w$]*(?=\()"
_COMMENTS: list[tuple[Kind, str]] = [("c", r"//.*"), ("c", _block(r"/\*", r"\*/"))]

JS_WORDS = (
    "abstract as async await break case catch class const continue debugger declare default delete do "
    "else enum export extends false finally for from function get if implements import in infer "
    "instanceof interface keyof let namespace new null of private protected public readonly return "
    "satisfies set static super switch this throw true try type typeof undefined var void while with yield"
)

_JS_RULES: list[tuple[Kind, str]] = [
    *_COMMENTS,
    ("s", _BT),
    ("s", _DQ),
    ("s", _SQ),
    ("k", _words(JS_WORDS)),
    ("t", _TYPE),
    ("f", _CALL),
    ("n", _NUMBER),
]
_JS = _grammar("JavaScript", _JS_RULES)
# A lookbehind cannot be an alternation of two widths in Python, so `<` and `</` become two of them.
_JSX = _grammar(
    "JavaScript JSX",
    [
        *_JS_RULES[:5],
        ("t", r"(?:(?<=<)|(?<=/))[A-Z][\w.]*"),
        ("k", r"(?:(?<=<)|(?<=/))[a-z][\w.-]*"),
        ("a", r"""\b[A-Za-z_][\w-]*(?==[{"'])"""),
        *_JS_RULES[5:],
    ],
)

_C_WORDS = (
    "abstract and as assert async auto await bool boolean break byte case catch char class const "
    "constexpr continue data def default defer delete do double else enum explicit export extends "
    "extern false final finally float for fun func function goto guard if implements import in inline "
    "instanceof int interface internal is let long mutable namespace new nil null object operator "
    "override package private protected public readonly register return sealed self short signed "
    "sizeof static struct super switch synchronized template this throw throws true try typedef "
    "typename union unsigned using val var virtual void volatile when where while yield"
)
_C = _grammar(
    "C",
    [
        *_COMMENTS,
        ("k", r"^\s*#\s*\w+"),
        ("s", _TRIPLE),
        ("s", _DQ),
        ("s", _SQ),
        ("f", r"@\w+"),
        ("a", r"\$\w+"),
        ("k", _words(_C_WORDS)),
        ("t", _TYPE),
        ("f", _CALL),
        ("n", _NUMBER),
    ],
)

_PYTHON = _grammar(
    "Python",
    [
        ("c", r"#.*"),
        ("s", _TRIPLE),
        ("s", _DQ),
        ("s", _SQ),
        ("f", r"@[\w.]+"),
        (
            "k",
            _words(
                "and as assert async await break case class continue def del elif else except False "
                "finally for from global if import in is lambda match None nonlocal not or pass raise "
                "return self True try while with yield"
            ),
        ),
        ("t", _TYPE),
        ("f", _CALL),
        ("n", _NUMBER),
    ],
)

_SHELL = _grammar(
    "Shell script",
    [
        ("c", r"(?<![\w$#{])#.*"),
        ("s", _DQ),
        ("s", r"'[^'\\\n]*'?"),
        ("a", r"\$\{[^}\n]*\}?|\$[\w@#?$!*-]"),
        (
            "k",
            _words(
                "if then else elif fi for in do done while until case esac function return local "
                "export readonly declare set unset shift exit source alias echo cd"
            ),
        ),
        ("n", _NUMBER),
    ],
)

_JSON = _grammar(
    "JSON",
    [
        *_COMMENTS,
        ("a", rf"{_DQ}(?=\s*:)"),
        ("s", _DQ),
        ("k", _words("true false null")),
        ("n", rf"-?{_NUMBER}"),
    ],
)

_YAML = _grammar(
    "YAML",
    [
        ("c", r"(?<!\S)#.*"),
        ("k", r"^(?:---|\.\.\.)$"),
        ("a", r"[\w.-][\w .-]*?(?=\s*:(?:\s|$))"),
        ("s", _DQ),
        ("s", _SQ),
        ("t", r"[&*][\w-]+"),
        ("k", _words("true false null")),
        ("n", _NUMBER),
    ],
)

_CONF = _grammar(
    "Configuration",
    [
        ("c", r"(?<!\S)[#;].*"),
        ("t", r"^\s*\[[^\]\n]*\]"),
        ("a", r"^\s*[\w.-]+(?=\s*[=:])"),
        ("s", _TRIPLE),
        ("s", _DQ),
        ("s", _SQ),
        ("k", _words("true false")),
        ("n", _NUMBER),
    ],
)

_DOCKER = _grammar(
    "Dockerfile",
    [
        ("c", r"^\s*#.*"),
        ("k", r"^\s*[A-Z]{2,}\b"),
        ("s", _DQ),
        ("s", _SQ),
        ("a", r"\$\{[^}\n]*\}?|\$\w+"),
        ("n", _NUMBER),
    ],
)

_MARKUP = _grammar(
    "HTML",
    [
        ("c", _block("<!--", "-->")),
        ("k", r"(?<=<)![A-Za-z]+"),
        ("k", r"(?:(?<=<)|(?<=/))[A-Za-z][\w:.-]*"),
        ("a", r"[\w:@.#-]+(?==)"),
        ("s", r'(?<==)"[^"]*"?'),
        ("s", r"(?<==)'[^']*'?"),
        ("n", r"&[\w#]+;"),
    ],
)

_CSS = _grammar(
    "CSS",
    [
        ("c", _block(r"/\*", r"\*/")),
        ("c", r"(?<![:\w])//.*"),
        ("s", _DQ),
        ("s", _SQ),
        ("k", r"@[\w-]+|!important"),
        ("n", r"#[\da-fA-F]{3,8}\b"),
        ("a", r"--[\w-]+|[\w-]+(?=\s*:\s)"),
        ("t", r"[.#][A-Za-z_-][\w-]*"),
        ("f", r"[\w-]+(?=\()"),
        ("", r"[A-Za-z_][\w-]*"),
        ("n", r"-?(?:\d+\.?\d*|\.\d+)(?:%|[A-Za-z]+)?"),
    ],
)

_MARKDOWN = _grammar(
    "Markdown",
    [
        ("c", r"^(?:```|~~~).*"),
        ("k", r"^#{1,6}\s.*"),
        ("c", r"^>.*"),
        ("n", r"^\s*(?:[-*+]|\d+[.)])(?=\s)"),
        ("s", r"`[^`\n]+`"),
        ("t", r"\*\*[^*\n]+\*\*|__[^_\n]+__"),
        ("a", r"!?\[[^\]\n]*\]\([^)\n]*\)"),
        ("f", r"<\/?[A-Za-z][^>\n]*>"),
    ],
)

_PLAIN = _grammar("Plain text", [])

_BY_EXTENSION: dict[str, Language] = {
    "js": Language("JavaScript", _JS.pattern, _JS.kinds),
    "mjs": Language("JavaScript", _JS.pattern, _JS.kinds),
    "cjs": Language("JavaScript", _JS.pattern, _JS.kinds),
    "jsx": _JSX,
    "ts": Language("TypeScript", _JS.pattern, _JS.kinds),
    "mts": Language("TypeScript", _JS.pattern, _JS.kinds),
    "cts": Language("TypeScript", _JS.pattern, _JS.kinds),
    "tsx": Language("TypeScript JSX", _JSX.pattern, _JSX.kinds),
    "json": Language("JSON", _JSON.pattern, _JSON.kinds),
    "jsonc": Language("JSON with comments", _JSON.pattern, _JSON.kinds),
    "json5": Language("JSON5", _JSON.pattern, _JSON.kinds),
    "jsonl": Language("JSON Lines", _JSON.pattern, _JSON.kinds),
    "html": Language("HTML", _MARKUP.pattern, _MARKUP.kinds),
    "htm": Language("HTML", _MARKUP.pattern, _MARKUP.kinds),
    "xml": Language("XML", _MARKUP.pattern, _MARKUP.kinds),
    "vue": Language("Vue", _MARKUP.pattern, _MARKUP.kinds),
    "svelte": Language("Svelte", _MARKUP.pattern, _MARKUP.kinds),
    "css": Language("CSS", _CSS.pattern, _CSS.kinds),
    "scss": Language("SCSS", _CSS.pattern, _CSS.kinds),
    "less": Language("Less", _CSS.pattern, _CSS.kinds),
    "md": Language("Markdown", _MARKDOWN.pattern, _MARKDOWN.kinds),
    "markdown": Language("Markdown", _MARKDOWN.pattern, _MARKDOWN.kinds),
    "mdx": Language("MDX", _MARKDOWN.pattern, _MARKDOWN.kinds),
    "py": Language("Python", _PYTHON.pattern, _PYTHON.kinds),
    "pyi": Language("Python", _PYTHON.pattern, _PYTHON.kinds),
    "c": Language("C", _C.pattern, _C.kinds),
    "h": Language("C header", _C.pattern, _C.kinds),
    "cpp": Language("C++", _C.pattern, _C.kinds),
    "cc": Language("C++", _C.pattern, _C.kinds),
    "cxx": Language("C++", _C.pattern, _C.kinds),
    "hpp": Language("C++ header", _C.pattern, _C.kinds),
    "cs": Language("C#", _C.pattern, _C.kinds),
    "java": Language("Java", _C.pattern, _C.kinds),
    "kt": Language("Kotlin", _C.pattern, _C.kinds),
    "php": Language("PHP", _C.pattern, _C.kinds),
    "zig": Language("Zig", _C.pattern, _C.kinds),
    "sh": Language("Shell script", _SHELL.pattern, _SHELL.kinds),
    "bash": Language("Shell script", _SHELL.pattern, _SHELL.kinds),
    "zsh": Language("Shell script", _SHELL.pattern, _SHELL.kinds),
    "fish": Language("Shell script", _SHELL.pattern, _SHELL.kinds),
    "yml": Language("YAML", _YAML.pattern, _YAML.kinds),
    "yaml": Language("YAML", _YAML.pattern, _YAML.kinds),
    "toml": Language("TOML", _CONF.pattern, _CONF.kinds),
    "ini": Language("INI", _CONF.pattern, _CONF.kinds),
    "cfg": Language("Configuration", _CONF.pattern, _CONF.kinds),
    "conf": Language("Configuration", _CONF.pattern, _CONF.kinds),
    "env": Language("Environment", _CONF.pattern, _CONF.kinds),
    "txt": _PLAIN,
    "text": _PLAIN,
    "log": _PLAIN,
    "csv": _PLAIN,
}

_BY_NAME: dict[str, Language] = {
    "dockerfile": _DOCKER,
    "containerfile": Language("Containerfile", _DOCKER.pattern, _DOCKER.kinds),
    ".bashrc": _SHELL,
    ".zshrc": _SHELL,
    ".profile": _SHELL,
    ".gitignore": Language("Ignore list", _CONF.pattern, _CONF.kinds),
    ".dockerignore": Language("Ignore list", _CONF.pattern, _CONF.kinds),
    ".npmignore": Language("Ignore list", _CONF.pattern, _CONF.kinds),
    ".editorconfig": _CONF,
    ".npmrc": _CONF,
    "license": _PLAIN,
}


def language_of(path: str) -> Language | None:
    """The language of the file at `path`, by its name or extension; none for what is neither code
    nor text (an SVG is a picture)."""
    name = path[path.rfind("/") + 1 :].lower()
    if name in _BY_NAME:
        return _BY_NAME[name]
    if name.startswith(".env"):
        return _BY_EXTENSION["env"]
    if name.startswith("dockerfile.") or name.endswith(".dockerfile"):
        return _BY_NAME["dockerfile"]
    dot = name.rfind(".")
    return _BY_EXTENSION.get(name[dot + 1 :]) if dot > 0 else None


def tokenize(source: str, language: Language) -> list[list[tuple[Kind, str]]]:
    """`source` cut into lines of tokens, in the language's kinds; the text between them a token too."""
    lines: list[list[tuple[Kind, str]]] = [[]]

    def push(kind: Kind, text: str) -> None:
        for i, piece in enumerate(text.split("\n")):
            if i > 0:
                lines.append([])
            if piece == "":
                continue
            line = lines[-1]
            if line and line[-1][0] == kind:
                line[-1] = (kind, line[-1][1] + piece)
            else:
                line.append((kind, piece))

    at = 0
    if language.pattern is not None:
        for match in language.pattern.finditer(source):
            if match.group(0) == "":
                continue
            if match.start() > at:
                push("", source[at : match.start()])
            group = next((i for i, got in enumerate(match.groups()) if got is not None), None)
            push(language.kinds[group] if group is not None else "", match.group(0))
            at = match.start() + len(match.group(0))
    push("", source[at:])
    return lines


def excerpt_of(text: str, language: Language, line: int | None, rows: int) -> Excerpt | None:
    """The `rows` lines a preview shows of `text`: the first ones, or from a few before `line` when
    it names one in the file, that one marked. Tabs are spaces, the indent they all share is cut,
    a long line is cut. None for a file with no text, or with what text never holds (a NUL)."""
    if text.strip() == "" or "\u0000" in text or text[:4096].count("\ufffd") > 8:
        return None
    everything = re.split(r"\r?\n", text)
    if len(everything) > 1 and everything[-1] == "":
        everything.pop()
    mark = line if line is not None and 1 <= line <= len(everything) else 0
    first = (
        1
        if mark == 0
        else max(1, min(mark - min(CONTEXT, rows // 3), len(everything) - rows + 1))
    )
    shown = [row.replace("\t", TAB).rstrip() for row in everything[first - 1 : first - 1 + rows]]
    while len(shown) > 1 and shown[-1] == "" and first + len(shown) - 1 != mark:
        shown.pop()
    indent = min((len(row) - len(row.lstrip()) for row in shown if row != ""), default=0)
    source = "\n".join(row[indent:][:LINE_CHARS] for row in shown)
    return Excerpt(language.name, len(everything), first, mark, source, tokenize(source, language))
