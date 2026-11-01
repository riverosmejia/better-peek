#!/usr/bin/env python3
"""Prepara la demo de docs/demo.gif: un proyecto de ejemplo y una sesion de Hermes que nombra rutas.

El transcript es siempre el mismo y no llama a ningun modelo, asi que la grabacion sale igual todas
las veces: no hay esperas, ni respuestas distintas, ni claves a la vista.

    python3 docs/seed-demo.py            crea /tmp/better-peek-demo y la sesion 'better-peek-demo'
    python3 docs/seed-demo.py --clean    la borra

Imprime el comando exacto para abrir el TUI en esa sesion.
"""
import os
import pathlib
import sqlite3
import sys
import time

SESSION = "better-peek-demo"
DEMO = pathlib.Path(os.environ.get("DEMO_DIR", "/tmp/better-peek-demo"))
HERMES_HOME = pathlib.Path(os.environ.get("HERMES_HOME", pathlib.Path.home() / ".hermes"))
DB = HERMES_HOME / "state.db"

FILLER = [
    "const MAX_RETRIES = 3",
    "type Handler = (err: Error) => void",
    "let attempts = 0",
    "export const timeout = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))",
    "const cache = new Map<string, Handler>()",
    "function normalize(name: string) { return name.trim().toLowerCase() }",
    "function retry(fn: () => void) { for (let i = 0; i < MAX_RETRIES; i++) fn() }",
    "const config = { port: 8080, host: '127.0.0.1' }",
    "async function health() { return { ok: true, attempts } }",
]

APP_TS = "\n".join(
    ["// demo: un fichero cualquiera, con algo que arreglar hacia la mitad", "import { createServer } from './server'", ""]
    + [FILLER[i % len(FILLER)] for i in range(35)]
    + [
        "",
        "export function listen(port: number) {",
        "  const server = createServer()",
        "  server.on('error', (err) => {",                       # 42
        "    // el bug: se pierde el listener al reconectar y el puerto queda tomado",
        "    console.error('listen failed', err)",
        "  })",
        "  return server.listen(port)",
        "}",
        "",
        "const stepTail = () => {}   // relleno final",
    ]
)

FILES = {
    "src/app.ts": APP_TS,
    "package.json": '{\n  "name": "demo",\n  "version": "0.1.0",\n  "type": "module",\n'
                    '  "scripts": { "dev": "vite", "build": "vite build" },\n'
                    '  "devDependencies": { "vite": "^6.0.0" }\n}\n',
    "README.md": "# demo\n\nProyecto de ejemplo para grabar la demo de better-peek.\n",
}

QUESTION = "Se cae al reconectar y el puerto sigue ocupado. ¿Dónde está el fallo?"

ANSWER = (
    "El fallo está en `src/app.ts:42`: el handler de `error` no se quita al reconectar, así que el "
    "listener viejo sigue vivo y el puerto nunca se libera.\n\n"
    "Dos cosas más mientras lo arreglas: `package.json` fija `vite` en `^6.0.0`, que ya no recibe "
    "parches, y el `README.md` no explica cómo se levanta el proyecto en local."
)


def write_project() -> None:
    for rel, content in FILES.items():
        path = DEMO / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def connect() -> sqlite3.Connection:
    if not DB.is_file():
        sys.exit(f"no encuentro {DB} (¿está Hermes instalado en otro HERMES_HOME?)")
    return sqlite3.connect(DB)


def clean(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM messages WHERE session_id = ?", (SESSION,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (SESSION,))
    conn.commit()


def seed(conn: sqlite3.Connection) -> None:
    clean(conn)
    now = time.time()
    conn.execute(
        "INSERT INTO sessions (id, source, model, started_at, last_activity_at, cwd, title, message_count)"
        " VALUES (?, 'cli', 'demo', ?, ?, ?, ?, 2)",
        (SESSION, now - 60, now, str(DEMO), "Demo de better-peek"),
    )
    for role, content, offset in (("user", QUESTION, 0), ("assistant", ANSWER, 30)):
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, active) VALUES (?, ?, ?, ?, 1)",
            (SESSION, role, content, now - 60 + offset),
        )
    conn.commit()


def main() -> None:
    conn = connect()
    if "--clean" in sys.argv:
        clean(conn)
        print(f"sesion {SESSION} borrada de {DB}")
        return
    write_project()
    seed(conn)
    print(f"proyecto: {DEMO}")
    print(f"sesion:   {SESSION} en {DB}")
    print("\nabre el TUI asi, y graba:\n")
    print(f"  cd {DEMO} && hermes chat --resume {SESSION} --tui")


if __name__ == "__main__":
    main()
