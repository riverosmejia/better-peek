# Grabar la demo

Objetivo: **10–12 s**, 1100 px de ancho, menos de 2 MB, que se entienda sin leer nada y que se pueda
repetir en bucle. Tres cosas, en este orden: ratón sobre una ruta, clic y fichero abierto, y `/peek`.

## Antes de grabar

```bash
python3 docs/seed-demo.py          # crea /tmp/better-peek-demo y una sesion con la respuesta
```

Deja escrito el comando para abrir el TUI en esa sesión:

```bash
cd /tmp/better-peek-demo && hermes chat --resume better-peek-demo --tui
```

La sesión está sembrada a mano: no llama a ningún modelo, así que no hay esperas ni respuestas
distintas entre tomas, y no aparece ninguna clave. La respuesta nombra `src/app.ts:42`,
`package.json` y `README.md`, y esos ficheros existen con esa línea.

Antes de darle a grabar, comprueba dos cosas:

- El parche está aplicado y el TUI reconstruido (`./patches/apply.sh`). Sin él las rutas no se
  resaltan y no hay clic: se grabaría la mitad de la historia.
- El ratón del terminal responde. Si estás dentro de tmux, el modo `wheel` rompe el hover.

## Grabar

Con `gpu-screen-recorder`, que ya viene instalado:

```bash
gpu-screen-recorder -w screen -f 30 -o ~/Videos/demo.mp4    # Ctrl+C para parar
```

Grabar la pantalla entera y recortar después es más fácil que acertar con las coordenadas de una
región. Al terminar, `./docs/to-gif.sh ~/Videos/demo.mp4` recorta a 1100 px, pasa a 12 fps, aplica
paleta en dos pasadas y avisa si pasa de 3 MB.

## El guion

Los tiempos son los del GIF final; si algo sale más lento, se recorta al montar.

| t | Qué se ve | Qué haces |
|---|---|---|
| 0,0 s | El transcript con la respuesta. Las rutas se distinguen del texto normal. | Nada. Un segundo quieto para que el ojo lea. |
| 1,5 s | El puntero entra en `src/app.ts:42` y aparece la tarjeta con las líneas de alrededor. | Mueve el ratón despacio, sin temblar, y déjalo encima. |
| 4,0 s | El fichero abierto en el visor del TUI, con la línea 42 marcada. | Clic en la ruta. |
| 6,0 s | El visor se cierra y vuelve el transcript. | `Esc`. |
| 7,0 s | Lista de las tres rutas, con tamaño y edad. | Escribe `/peek` y `Enter`. |
| 9,0 s | La tarjeta de `app.ts` con la línea 42 marcada. | Escribe `/peek 1` y `Enter`. |
| 11,0 s | Fin. | Para la grabación. |

Si el GIF queda largo, el plano de `/peek 1` es el que se cae: los dos primeros planos ya cuentan lo
que nadie más tiene.

## Qué no puede salir

- Ninguna otra ventana, ni notificaciones: `gpu-screen-recorder -w screen` graba todo.
- Ninguna sesión real. Por eso la demo usa una sesión sembrada y no tu historial.
- Nada de la barra de estado que delate una clave: la sesión sembrada no tiene proveedor.

## Al terminar

```bash
python3 docs/seed-demo.py --clean     # borra la sesion de demo de state.db
```

Y el GIF va a `docs/demo.gif`. En el README es una línea, justo debajo del titular:

```markdown
![demo](docs/demo.gif)
```
