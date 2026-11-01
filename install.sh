#!/usr/bin/env bash
# Instala better-peek en el Hermes de este usuario: el plugin (/peek) y su widget del TUI
# (/better-peek). Copia el plugin a ~/.hermes/plugins/better-peek y enlaza el widget.
#
#   ./install.sh            instala, habilita y comprueba
#   ./install.sh --check    solo comprueba (no cambia nada)
#   ./install.sh --link     en vez de copiar, enlaza este checkout (para desarrollar)
#
# Idempotente. No toca nada más que esos dos sitios y la lista de plugins habilitados.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
NAME="better-peek"
TARGET="$HERMES_HOME/plugins/$NAME"
WIDGET="$HERE/tui-widgets/$NAME.mjs"
FILES=(plugin.yaml plugin.json __init__.py peek_paths.py peek_code.py peek_cli.py)
MODE=install

for arg in "$@"; do
  case "$arg" in
    --check) MODE=check ;;
    --link) MODE=link ;;
    *) printf 'opción desconocida: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
say() { printf '\n== %s\n' "$1"; }

for file in "${FILES[@]}"; do [ -f "$HERE/$file" ] || fail "falta $file en $HERE"; done
[ -f "$WIDGET" ] || fail "falta $WIDGET"

HERMES="$(command -v hermes || true)"
[ -n "$HERMES" ] || HERMES="$HERMES_HOME/hermes-agent/venv/bin/hermes"
[ -x "$HERMES" ] || fail "no encuentro el binario de hermes (PATH ni $HERMES_HOME/hermes-agent/venv/bin)"

say "entorno"
printf 'repo:         %s\n' "$HERE"
printf 'hermes home:  %s\n' "$HERMES_HOME"
printf 'hermes:       %s\n' "$HERMES"
"$HERMES" --version 2>&1 | head -1
printf 'python:       %s\n' "$(python3 --version 2>&1)"

say "tests"
python3 -m unittest discover -s "$HERE/tests" -q 2>&1 | tail -3

if [ "$MODE" = check ]; then
  printf '\n--check: no se tocó nada. destino: %s\n' "$TARGET"
  if [ -e "$TARGET" ]; then printf '  ya existe\n'; else printf '  no instalado\n'; fi
  exit 0
fi

say "$([ "$MODE" = link ] && echo enlazando || echo copiando)"
mkdir -p "$HERMES_HOME/plugins" "$HERMES_HOME/tui-widgets"
rm -rf "$TARGET"

if [ "$MODE" = link ]; then
  ln -sfn "$HERE" "$TARGET"
  printf '  %s -> %s\n' "$TARGET" "$HERE"
else
  mkdir -p "$TARGET"
  for file in "${FILES[@]}"; do cp -f "$HERE/$file" "$TARGET/$file"; done
  cp -R "$HERE/tests" "$TARGET/tests"
  chmod 644 "$TARGET"/*.py "$TARGET"/*.yaml "$TARGET"/*.json
  printf '  %s (%s ficheros + tests)\n' "$TARGET" "${#FILES[@]}"
fi

ln -sfn "$WIDGET" "$HERMES_HOME/tui-widgets/$NAME.mjs"
printf '  %s -> %s\n' "$HERMES_HOME/tui-widgets/$NAME.mjs" "$WIDGET"

say "habilitando"
"$HERMES" plugins enable "$NAME" 2>&1 | tail -2

say "comprobación"
"$HERMES" plugins doctor "$NAME" 2>&1 | tail -3
ls -l "$TARGET" | head -4 | sed 's/^/  /'

printf '\nlisto. Para probarlo:\n'
printf '  %s chat -q "/peek /etc/os-release"     (sin modelo, imprime la tarjeta)\n' "$HERMES"
printf '  %s --tui   y luego  /better-peek ⏎      (modal: flechas, Enter, c, esc)\n' "$HERMES"
printf '\nOpcional: ./patches/apply.sh   (rutas enlazadas y tarjeta al pasar el ratón)\n'
