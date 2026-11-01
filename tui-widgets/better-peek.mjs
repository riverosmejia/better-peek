// better-peek — the paths of the last answer, and a look at one, inside the TUI.
//
// The port of quick-peek's hover to a terminal that has no pointer: /better-peek opens a modal
// list, ↑/↓ picks, Enter shows the file with its lines numbered and the one the path names
// marked, c copies `path:line`, Esc closes (or goes back to the list from a file).
//
// No JSX and no bare imports beyond node's own: everything else comes from the sdk parameter.
// The data comes from peek_cli.py (the plugin next door), the same code /peek uses.
import { execFile, spawn } from 'node:child_process'
import { readFileSync, statSync } from 'node:fs'

export default function register(sdk) {
  const { Box, Dialog, Overlay, Text, defineWidgetApp, h, updateWidget } = sdk

  const HERMES_HOME = process.env.HERMES_HOME || `${process.env.HOME || ''}/.hermes`
  const WIDTH = 78
  const ROWS = 22

  const CLI = [new URL('../peek_cli.py', import.meta.url).pathname,
    `${HERMES_HOME}/plugins/better-peek/peek_cli.py`]
    .find(path => { try { return statSync(path).isFile() } catch { return false } })

  /** This TUI's session, as the host publishes it (same file the OMH widget reads). */
  const sessionId = () => {
    const file = process.env.HERMES_TUI_ACTIVE_SESSION_FILE
    if (!file) return ''
    try {
      if (!statSync(file).isFile() || statSync(file).size > 4096) return ''
      const parsed = JSON.parse(readFileSync(file, 'utf8'))
      return typeof parsed?.session_id === 'string' ? parsed.session_id : ''
    } catch { return '' }
  }

  const run = (args, done) => {
    if (!CLI) return done('peek_cli.py no está: revisa el symlink del plugin')
    execFile('python3', [CLI, ...args], { timeout: 15000, maxBuffer: 4 << 20 }, (error, stdout, stderr) => {
      if (error && !stdout) return done(String(stderr || error.message).trim().split('\n')[0])
      done(null, String(stdout))
    })
  }

  const copy = text => {
    try {
      const child = spawn('wl-copy', [], { stdio: ['pipe', 'ignore', 'ignore'] })
      child.stdin.end(text)
      return true
    } catch { return false }
  }

  const app = defineWidgetApp({
    id: 'better-peek',
    help: 'the paths of the last answer, and a look at one',
    mode: 'modal',
    width: WIDTH,
    init: arg => {
      const state = { hits: [], index: 0, lines: [], view: 'list', note: 'leyendo el último mensaje…' }
      const session = sessionId()
      const target = String(arg || '').trim()

      const show = next => updateWidget(app, () => next)
      const list = done => run(session ? ['--session', session, '--machine', 'json'] : ['--machine', 'json'], (error, out) => {
        if (error) return done({ ...state, note: error })
        let hits = []
        try { hits = JSON.parse(out) } catch { return done({ ...state, note: 'respuesta ilegible de peek_cli' }) }
        done({ ...state, hits, note: hits.length ? '' : 'sin rutas en el último mensaje' })
      })

      list(first => {
        if (!target) return show(first)
        const pick = /^\d+$/.test(target) ? Number(target) - 1 : first.hits.findIndex(hit => hit.label === target || hit.path === target)
        // A path that is not in the list is still peekable: the CLI takes it as its target.
        const ask = pick >= 0 ? String(pick + 1) : target
        run([ask, '--rows', String(ROWS)], (error, out) => {
          show({ ...first, index: Math.max(0, pick), view: 'card', lines: error ? [error] : out.replace(/\n$/, '').split('\n') })
        })
      })
      return state
    },
    reduce: (state, { ch, key }) => {
      const { hits, index, view } = state
      const goBack = () => ({ ...state, view: 'list', lines: [], note: '' })

      if (key.escape) return view === 'card' ? goBack() : null
      if (ch === 'q') return view === 'card' ? goBack() : null
      if (view === 'card') {
        if (ch === 'c') {
          const hit = hits[index]
          const text = hit ? `${hit.path}${hit.line ? `:${hit.line}` : ''}` : ''
          return { ...state, note: hit && copy(text) ? `copiado ${text}` : 'sin portapapeles' }
        }
        return state
      }
      if (key.upArrow || ch === 'k') return { ...state, index: Math.max(0, index - 1) }
      if (key.downArrow || ch === 'j') return { ...state, index: Math.min(Math.max(0, hits.length - 1), index + 1) }
      if (key.return || ch === 'l') {
        const hit = hits[index]
        if (!hit) return state
        const session = sessionId()
        let next = { ...state, view: 'card', lines: ['abriendo…'], note: '' }
        run(['--session', session || '', '--rows', String(ROWS), String(index + 1)], (error, out) => {
          updateWidget(app, current => ({ ...current, lines: error ? [error] : out.replace(/\n$/, '').split('\n') }))
        })
        return next
      }
      if (ch === 'c' && hits[index]) {
        const hit = hits[index]
        const text = `${hit.path}${hit.line ? `:${hit.line}` : ''}`
        return { ...state, note: copy(text) ? `copiado ${text}` : 'sin portapapeles' }
      }
      return state
    },
    render: ({ state, t }) => {
      const row = hit => {
        const where = hit.line ? `:${hit.line}` : ''
        const chosen = state.hits.indexOf(hit) === state.index
        return h(Text, { key: `${hit.path}${where}`, color: chosen ? t.color.accent : t.color.label },
          `${chosen ? '❯' : ' '} ${hit.label}${where}`)
      }
      const body = state.view === 'card'
        ? state.lines.map((line, i) => h(Text, { key: `l${i}`, color: line.startsWith('▸') ? t.color.accent : t.color.label }, line))
        : (state.hits.length
            ? state.hits.map(row)
            : [h(Text, { key: 'empty', color: t.color.muted }, state.note || 'sin rutas')])
      const hint = state.view === 'card'
        ? 'esc volver · c copiar · q cerrar'
        : '↑↓ elegir · ⏎ ver · c copiar · esc cerrar'
      return h(Overlay, null, h(Dialog, { width: WIDTH, title: state.view === 'card' ? 'peek' : 'peek · rutas del último mensaje' },
        h(Box, { flexDirection: 'column' }, ...body,
          h(Text, { color: t.color.muted }, state.note && state.hits.length ? state.note : hint))))
    }
  })
  return app
}
