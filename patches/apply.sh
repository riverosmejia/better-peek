#!/usr/bin/env bash
# Aplica los parches de este repo al Hermes instalado y reconstruye el TUI.
#
#   ./apply.sh                 aplica lo que falte y compila
#   ./apply.sh --check         dice si la base es la esperada, sin tocar nada
#   ./apply.sh --no-build      aplica, pero no compila (lo haces tú después)
#
# Los parches son de `ui-tui` (y del fork de ink que vive dentro): Hermes no da
# ninguna costura para que un plugin dibuje dentro de un mensaje, así que las
# rutas del transcript se enlazan y se previsualizan parcheando el TUI.
#
# Van en serie: cada uno se apoya en el anterior. Por eso solo se comprueba que
# el PRIMERO aplique (si aplica, la base es la esperada) y luego se aplican en
# orden, parando en el primero que falle. Idempotente: con los parches ya
# puestos no hace nada.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CHECKOUT="${HERMES_CHECKOUT:-$HERMES_HOME/hermes-agent}"
UI="$CHECKOUT/ui-tui"
MARKER="$UI/src/lib/paths.ts"
CHECK_ONLY=0
BUILD=1

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --no-build) BUILD=0 ;;
    *) printf 'opción desconocida: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$1"; }
fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

[ -e "$CHECKOUT/.git" ] || fail "no encuentro el checkout de Hermes en $CHECKOUT (usa HERMES_CHECKOUT=...)"
[ -d "$UI" ] || fail "falta $UI"

say "entorno"
"$CHECKOUT/venv/bin/hermes" --version 2>/dev/null | head -1 || true
printf 'checkout: %s\n' "$CHECKOUT"
printf 'rama:     %s\n' "$(git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD)"

if [ -f "$MARKER" ] && grep -q "hermes-peek" "$MARKER" 2>/dev/null; then
  say "ya está aplicado"
  printf 'nada que hacer. Para reaplicar desde cero: git -C %s checkout -- ui-tui\n' "$CHECKOUT"
  exit 0
fi

say "parches"
first="$(ls "$HERE"/*.patch | head -1)"
patch -p1 -d "$CHECKOUT" --fuzz=3 --forward --dry-run < "$first" >/dev/null 2>&1 ||
  fail "el primer parche no aplica sobre $(git -C "$CHECKOUT" rev-parse --short HEAD): ¿otra versión de Hermes?"
printf '  la base es la esperada (%s)\n' "$(basename "$first")"

[ "$CHECK_ONLY" = 1 ] && { printf '\n--check: no se tocó nada.\n'; exit 0; }

say "aplicando"
for patch_file in "$HERE"/*.patch; do
  printf '  %s ... ' "$(basename "$patch_file")"

  if out="$(patch -p1 -d "$CHECKOUT" --fuzz=3 --forward < "$patch_file" 2>&1)"; then
    printf 'ok\n'
  else
    printf 'FALLA\n'
    printf '%s\n' "$out" | sed 's/^/    /'
    printf '\nlos parches anteriores sí quedaron aplicados. Para volver atrás:\n'
    printf '  git -C %s checkout -- ui-tui\n' "$CHECKOUT"
    exit 1
  fi
done

if [ "$BUILD" = 1 ]; then
  [ -d "$UI/node_modules" ] || fail "falta $UI/node_modules: abre el TUI una vez (hermes --tui) o corre npm install ahí"

  say "compilando el TUI (ink incluido)"
  (cd "$UI" && npm run build:ink 2>&1 | tail -2 && npm run build 2>&1 | tail -2)
else
  say "sin compilar (--no-build): recuerda 'npm run build:ink && npm run build' en $UI"
fi

printf '\nlisto. Reinicia el TUI: hermes --tui\n'
