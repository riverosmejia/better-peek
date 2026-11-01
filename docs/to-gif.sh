#!/usr/bin/env bash
# Convierte la grabacion de la demo en docs/demo.gif, lista para el README.
#
#   ./docs/to-gif.sh ~/Videos/demo.mp4              -> docs/demo.gif a 1100 px
#   ./docs/to-gif.sh ~/Videos/demo.mp4 out.gif 900  -> otro nombre y ancho
#
# 12 fps, paleta en dos pasadas (la unica forma de que un GIF no se vea sucio) y aviso si el fichero
# pasa de 3 MB, que es donde GitHub empieza a tardar en servirlo.
set -euo pipefail

IN="${1:-}"
OUT="${2:-docs/demo.gif}"
WIDTH="${3:-1100}"
LIMIT_KB=3072

[ -n "$IN" ] || { printf 'uso: %s entrada.mp4 [salida.gif] [ancho]\n' "${BASH_SOURCE[0]}" >&2; exit 2; }
[ -f "$IN" ] || { printf 'ERROR: no existe %s\n' "$IN" >&2; exit 1; }

mkdir -p "$(dirname "$OUT")"
PAL="$(mktemp --suffix=.png)"
trap 'rm -f "$PAL"' EXIT

FILTER="fps=12,scale=${WIDTH}:-1:flags=lanczos"
ffmpeg -v error -y -i "$IN" -vf "$FILTER,palettegen=stats_mode=diff" "$PAL"
ffmpeg -v error -y -i "$IN" -i "$PAL" \
  -lavfi "$FILTER[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle" \
  -loop 0 "$OUT"

KB=$(( $(stat -c %s "$OUT") / 1024 ))
printf 'listo: %s  (%s KB, %sx?)\n' "$OUT" "$KB" "$WIDTH"
if [ "$KB" -gt "$LIMIT_KB" ]; then
  printf 'AVISO: pasa de %s KB. Baja el ancho (o recorta segundos): %s entrada.mp4 %s 900\n' \
    "$LIMIT_KB" "${BASH_SOURCE[0]}" "$OUT" >&2
  exit 3
fi
