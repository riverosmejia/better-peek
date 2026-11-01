"""The cases the original ships (plugins/quick-peek/hooks/register.test.tsx, lines 70-102), plus
the ones for candidates(), which is the only thing this port adds on top.

Run: python3 -m unittest discover -s hermes/plugins/better-peek/tests
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from peek_code import excerpt_of, language_of, tokenize  # noqa: E402
from peek_cli import card, listing  # noqa: E402
from peek_paths import Hit, candidates, line_of, path_of_span, paths_in, resolve  # noqa: E402

VIDEO = "/Users/ana/videos/borrador.mp4"
FOLDER = "/Users/ana/videos"
README = "/project/app/README.md"
SOURCE = "/project/app/src/app.ts"
CODE = "\n".join(
    [
        "import { run } from './run'",
        "",
        "// Starts it",
        "export async function start (port: number) {",
        "  const server = await run(port)",
        "  return server",
        "}",
        "",
    ]
)


def found(text: str) -> list[list[str]]:
    return [[text[f.start : f.end], f.target] for f in paths_in(text)]


def lang(path: str):
    language = language_of(path)
    assert language is not None, path
    return language


def excerpt(text: str, path: str, line: int | None, rows: int):
    got = excerpt_of(text, lang(path), line, rows)
    assert got is not None, path
    return got


class Paths(unittest.TestCase):
    def test_finds_absolute_home_relative_and_bare_paths_and_cuts_what_a_sentence_adds(self):
        self.assertEqual(
            found("Lo dejé en /Users/ana/x.mp4. Y en ~/notas.md, ¿vale?"),
            [["/Users/ana/x.mp4", "/Users/ana/x.mp4"], ["~/notas.md", "~/notas.md"]],
        )
        self.assertEqual(
            found("Mira src/app.ts:42 y README.md (la raíz)."),
            [["src/app.ts:42", "src/app.ts"], ["README.md", "README.md"]],
        )
        self.assertEqual(
            found("see https://example.com/a/b.html and/or 1/2"),
            [["and/or", "and/or"], ["1/2", "1/2"]],
        )
        self.assertEqual(found("a word, then this"), [])

    def test_a_span_may_hold_spaces(self):
        self.assertEqual(path_of_span("~/My Videos/a b.mp4"), "~/My Videos/a b.mp4")
        self.assertIsNone(path_of_span("npm run build"))

    def test_resolve_folds_dots_and_expands_home(self):
        self.assertEqual(resolve("../b/./c.txt", "/project/app", "/Users/ana"), "/project/b/c.txt")
        self.assertEqual(resolve("~/x", "/project/app", "/Users/ana"), "/Users/ana/x")
        self.assertIsNone(resolve("~/x", "/project/app", None))

    def test_line_of(self):
        self.assertEqual(line_of("src/app.ts:42"), 42)
        self.assertEqual(line_of("src/app.ts:42:7."), 42)
        self.assertIsNone(line_of("src/app.ts"))


class Candidates(unittest.TestCase):
    """The piece this port adds: which of the paths a text names actually lead somewhere."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.app = base / "app"
        (self.app / "src").mkdir(parents=True)
        (self.app / "README.md").write_text("# hola\n")
        (self.app / "src" / "app.ts").write_text("const a = 1\n")
        (base / "home").mkdir()
        (base / "home" / "notas.md").write_text("notas\n")
        self.addCleanup(self.tmp.cleanup)

    def test_keeps_only_what_exists_in_order_and_deduped(self):
        text = f"mira {self.app}/README.md y src/app.ts y otra vez {self.app}/README.md, y nada.mp4"
        hits = candidates(text, str(self.app), str(self.app), str(self.app.parent / "home"))
        self.assertEqual([h.path for h in hits], [f"{self.app}/README.md", f"{self.app}/src/app.ts"])
        self.assertEqual([h.label for h in hits], [f"{self.app}/README.md", "src/app.ts"])

    def test_a_relative_path_leads_from_the_project_after_a_cd(self):
        text = "el fix está en src/app.ts:1 y en README.md"
        hits = candidates(text, str(self.app / "src"), str(self.app), str(self.app.parent / "home"))
        self.assertEqual(
            [(h.path, h.line) for h in hits],
            [(f"{self.app}/src/app.ts", 1), (f"{self.app}/README.md", None)],
        )

    def test_home_and_spans_with_spaces(self):
        home = self.app.parent / "home"
        (home / "My Videos").mkdir()
        (home / "My Videos" / "a b.mp4").write_bytes(b"x")
        hits = candidates("en `~/My Videos/a b.mp4` esta", str(self.app), str(self.app), str(home))
        self.assertEqual([h.path for h in hits], [str(home / "My Videos" / "a b.mp4")])

    def test_urls_and_missing_paths_are_dropped_and_the_limit_holds(self):
        text = "https://example.com/a/b.html y /no/existe/x.ts y src/app.ts y README.md"
        hits = candidates(text, str(self.app), str(self.app), str(self.app.parent / "home"))
        self.assertEqual([h.label for h in hits], ["src/app.ts", "README.md"])
        self.assertEqual(len(candidates(text, str(self.app), None, None, limit=1)), 1)


class Code(unittest.TestCase):
    def test_language_by_name_or_extension(self):
        names = [
            (lambda language: language.name if language else None)(language_of(p))
            for p in ["a.ts", "b.tsx", "c.html", "d.css", "e.json", "f.md", "Dockerfile", ".env.local", "g.svg", "h.mp4"]
        ]
        self.assertEqual(
            names,
            ["TypeScript", "TypeScript JSX", "HTML", "CSS", "JSON", "Markdown", "Dockerfile", "Environment", None, None],
        )

    def test_tokenize(self):
        self.assertEqual(
            tokenize('const a = "x" // y', lang("a.js")),
            [[("k", "const"), ("", " a = "), ("s", '"x"'), ("", " "), ("c", "// y")]],
        )
        self.assertEqual(
            tokenize('<a href="/x">hi</a>', lang("a.html"))[0],
            [("", "<"), ("k", "a"), ("", " "), ("a", "href"), ("", "="), ("s", '"/x"'), ("", ">hi</"), ("k", "a"), ("", ">")],
        )
        self.assertEqual(
            tokenize(".card { color: #fff; }", lang("a.css"))[0],
            [("t", ".card"), ("", " { "), ("a", "color"), ("", ": "), ("n", "#fff"), ("", "; }")],
        )
        # A block comment that spans lines is a comment on each.
        self.assertEqual(
            tokenize("/* a\nb */ x", lang("a.ts")),
            [[("c", "/* a")], [("c", "b */"), ("", " x")]],
        )

    def test_excerpt_of(self):
        first = excerpt(CODE, SOURCE, None, 3)
        self.assertEqual(
            (first.language, first.count, first.first, first.mark, first.source),
            ("TypeScript", 7, 1, 0, "import { run } from './run'\n\n// Starts it"),
        )
        around = excerpt(CODE, SOURCE, 5, 3)
        self.assertEqual(
            (around.first, around.mark, around.source),
            (4, 5, "export async function start (port: number) {\n  const server = await run(port)\n  return server"),
        )
        # Tabs are spaces and the indent they all share is cut.
        self.assertEqual(excerpt("    a\n\tb\n      c", SOURCE, None, 5).source, "  a\nb\n    c")
        # Past its end, the line names nothing; a file with a NUL, or none, shows no lines.
        beyond = excerpt(CODE, SOURCE, 99, 3)
        self.assertEqual((beyond.first, beyond.mark), (1, 0))
        self.assertIsNone(excerpt_of("G\u0000\u0000x", lang(SOURCE), None, 3))
        self.assertIsNone(excerpt_of("\n  \n", lang(SOURCE), None, 3))


class Card(unittest.TestCase):
    """The text /peek prints: a listing of what the last message names, and one path's card."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.script = self.dir / "start.py"
        self.script.write_text("import os\n\n\ndef start(port):\n    return port\n")

    def test_listing_numbers_the_hits_with_size_age_and_line(self):
        hits = candidates(f"{self.script}:4", str(self.dir), None, str(self.dir))
        out = listing(hits)
        self.assertTrue(out.startswith("1  "), out)
        self.assertIn("start.py:4", out)
        self.assertEqual(listing([]), "no paths in the last message")

    def test_card_numbers_the_lines_and_marks_the_one_named(self):
        out = card(candidates(f"{self.script}:4", str(self.dir), None, str(self.dir))[0])
        self.assertIn("Python, 5 lines", out)
        self.assertIn("▸   4  def start(port):", out)

    def test_card_of_a_binary_and_of_a_folder(self):
        binary = self.dir / "blob.py"
        binary.write_bytes(b"a\x00b")
        self.assertIn("(no preview)", card(Hit("blob.py", str(binary))))
        self.assertIn("dir,", card(Hit("tmp", str(self.dir))))


if __name__ == "__main__":
    unittest.main()
