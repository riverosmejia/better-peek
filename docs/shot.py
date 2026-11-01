#!/usr/bin/env python3
"""Captura un PNG del TUI de Hermes mostrando la tarjeta de better-peek, sin GUI.

Corre `hermes chat --resume <sesion> --tui` en un pty, escribe `/peek 1` como lo haria una persona,
lee la salida ANSI con pyte y la rasteriza con PIL. Es la interfaz de verdad, con el texto de verdad,
y sale igual todas las veces.

    pip install pyte pillow
    python3 docs/seed-demo.py          # la sesion y el proyecto de ejemplo
    python3 docs/shot.py docs/demo.png
"""
import fcntl
import os
import pty
import re
import select
import struct
import sys
import termios
import time

import pyte
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 128, 34
FONTS = ("/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf",
         "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
         "/usr/share/fonts/noto/NotoSansMono-Regular.ttf")
BORDER = set("║╔╗╚╝═╭╮╰╯│─┌┐└┘")
FONT_SIZE = 15
LINE_SPACING = 3
PAD = 18
BG = (24, 24, 28)
FG = (222, 222, 226)
ANSI = {
    "black": (40, 40, 46), "red": (224, 108, 117), "green": (152, 195, 121),
    "brown": (229, 192, 123), "blue": (97, 175, 239), "magenta": (198, 120, 221),
    "cyan": (86, 182, 194), "white": (220, 223, 228),
}


def spawn(argv, cwd):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update({"TERM": "xterm-256color", "COLORTERM": "truecolor", "LANG": "C.UTF-8"})
        os.chdir(cwd)
        os.execvp(argv[0], argv)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    return pid, fd


def pump(fd, stream, seconds):
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            continue
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        # Un pty no contesta a las consultas del terminal; lo hacemos nosotros para que la app no
        # crea que esta sola y apague cosas a media captura.
        for probe, reply in ((b"\x1b[?1000$p", b"\x1b[?1000;1$y"), (b"\x1b[c", b"\x1b[?62;22c"),
                             (b"\x1b]11;?\x07", b"\x1b]11;rgb:1818/1818/1c1c\x07"),
                             (b"\x1b]10;?\x07", b"\x1b]10;rgb:dede/deee/e6e6\x07")):
            if probe in data:
                try:
                    os.write(fd, reply)
                except OSError:
                    pass
        stream.feed(data)


def color_of(token):
    if token in ANSI:
        return ANSI[token]
    if token == "default":
        return FG
    m = re.match(r"#?([0-9a-fA-F]{6})$", token or "")
    if m:
        v = int(m.group(1), 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    return FG


class Fonts:
    """Primera fuente que tenga el glifo: el logo usa bloques que no estan en todas."""

    def __init__(self):
        self.loaded = [ImageFont.truetype(p, FONT_SIZE) for p in FONTS]
        self.cache = {}

    def get(self, ch):
        if ch in self.cache:
            return self.cache[ch]
        pick = self.loaded[0]
        for font in self.loaded:
            try:
                if font.getmask(ch).getbbox():
                    pick = font
                    break
            except OSError:
                continue
        self.cache[ch] = pick
        return pick


def raster(screen, path):
    fonts = Fonts()
    cw = int(fonts.loaded[0].getlength("M"))
    ch = FONT_SIZE + LINE_SPACING
    # fuera la barra de OMH del usuario: en una imagen publica no va el kanban de su trabajo
    bottom = next((y for y in range(ROWS) if "[OMH]" in screen.display[y]), ROWS)

    # recorta al modal: del texto de cabecera hacia fuera hasta los bordes de SU marco, y en
    # vertical mientras ese borde siga ahi. Asi no entra el transcript que asoma por detras.
    x0, x1, y0, y1 = 0, COLS, 0, bottom
    hy = next((y for y in range(bottom) if "TypeScript" in screen.display[y]), None)
    if hy is not None:
        edge = "║│"
        hx = screen.display[hy].index("TypeScript")
        lefts = [x for x in range(hx) if screen.buffer[hy][x].data in edge]
        rights = [x for x in range(hx, COLS) if screen.buffer[hy][x].data in edge]
        if lefts and rights:
            lo, hi = lefts[-1], rights[0]
            y0 = hy
            while y0 > 0 and screen.buffer[y0 - 1][lo].data in edge:
                y0 -= 1
            y1 = hy
            while y1 + 1 < bottom and screen.buffer[y1 + 1][lo].data in edge:
                y1 += 1
            x0, x1 = max(0, lo), min(COLS, hi + 1)
            y0, y1 = max(0, y0 - 1), min(bottom, y1 + 2)

    img = Image.new("RGB", (PAD * 2 + cw * (x1 - x0), PAD * 2 + ch * (y1 - y0)), BG)
    draw = ImageDraw.Draw(img)
    for y in range(y0, y1):
        row = screen.buffer[y]
        for x in range(x0, x1):
            cell = row[x]
            if cell.data.strip():
                draw.text((PAD + (x - x0) * cw, PAD + (y - y0) * ch), cell.data,
                          font=fonts.get(cell.data), fill=color_of(cell.fg))
    img.save(path)
    return img.size


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "demo.png"
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)
    pid, fd = spawn(["hermes", "chat", "--resume", "better-peek-demo", "--tui"],
                    cwd="/tmp/better-peek-demo")
    pump(fd, stream, 10.0)
    for ch in "/peek 1":
        os.write(fd, ch.encode())
        pump(fd, stream, 0.06)
    os.write(fd, b"\r")
    pump(fd, stream, 4.0)

    size = raster(screen, out)
    print(f"escrito {out} {size[0]}x{size[1]}")
    print("linea 42 en pantalla:", "server.on" in "\n".join(screen.display))
    os.kill(pid, 9)


if __name__ == "__main__":
    main()
