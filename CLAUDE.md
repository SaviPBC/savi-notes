# Savi Notes

The shareable, cross-platform version of Wolfen Notes, the notes app in Ross
Mountjoy's Wolfen desktop (`~/Work/wolfen-os/shell/apps/notes`). It is meant
for Ross's colleagues at Savi on Windows and macOS: they paste the prompt in
`README.md` into Claude Code, which installs the app with `uv`; the app's
first launch asks where to keep notes and installs its own Claude Code skill.
Notes are plain markdown files organised by tags, never folders.

Status (2026-10-17): works on Linux end to end; not yet run on macOS or
Windows; not yet pushed to GitHub. The home is the SaviPBC GitHub org, as a
public repo named `savi-notes`. Ross's `gh` login (`rmountjoy92`) could not
see that org at the time; he needs to be invited, or log in with his Savi
account, before the first push. Then: create the repo, push `main`, tag
`v0.1.0` (the release workflow publishes the release the updater reads).

## Layout

- `src/savi_notes/app.py` — the Qt Quick host (PySide6): loads the QML, runs
  the engine as a child process (`EngineBridge`), keeps one window per
  settings file (a second launch hands its note to the first), exports PDFs
  with `QTextDocument`, checks GitHub's latest release and runs the update.
- `src/savi_notes/engine.py` — everything done to the vault: scan, read,
  save, rename (fixing `[[links]]`), trash, attachments, hybrid search (words
  plus llama.cpp embeddings), git sync, remote images, math (ziamath, in
  process) and mermaid (external `mmdr` or `mmdc` only). JSON lines on
  stdin/stdout; `python -m savi_notes.engine serve VAULT`.
- `src/savi_notes/qml/` — the window. `NotesWindow.qml` (root `Window`),
  `NotePane.qml` (one open note's state and saving), `PaneTree.qml` (splits),
  `NoteView.qml` (reader/editor, toolbar host), `Finder.qml` (Shift twice:
  This file / Notes / Tags / Settings), `FormatBar.qml` + `PopupMenu.qml`
  (toolbar and Insert menu), `Onboarding.qml` (first run), `Engine.qml`
  (call/reply over `EngineBridge`), `Markdown.js` (markdown → Qt rich text).
- `src/savi_notes/qml/Savi/` — the theme module (`import Savi`): `Style`
  (sizes, fonts, `ctrl` = ⌘ on Mac), `Colors` (Savi palette, dark/light),
  `Util`, `Border`, `BorderSurface`, `PanelToolTip`, `ConfirmDialog`.
- `cli.py` (`savi-notes …`), `config.py` (platformdirs; `config.json` with
  `vault`, `semantic`, `sync`, `theme`), `llama.py` (per-OS llama.cpp
  download from a pinned release), `mathsvg.py`, `update.py`, `skill.py`
  (installs `skill/SKILL.md` into `~/.claude/skills/savi-notes`, re-copied
  on every launch when it differs), `shortcuts.py` (Start Menu / `.app` /
  `.desktop`), `vaultcheck.py` (`savi-notes check`), `FORMAT.md` (every
  markdown syntax the renderer supports; the skill reads it through
  `savi-notes format`), `fonts/` (Nerd Font symbols, MIT), `icon.svg` (Savi's
  V mark, colours from app.bysavi.com's favicon).
- `scripts/boot_test.py` — starts the app headless and fails on QML or
  engine complaints; CI runs it on Ubuntu, macOS and Windows.

## Running and testing

```sh
uv sync                       # Python 3.13; PySide6-Essentials, numpy, send2trash, platformdirs, ziamath
uv run savi-notes             # or: uv run savi-notes "Note title"
uv run python scripts/boot_test.py
uv build                      # the wheel must include qml/, fonts/, skill/, FORMAT.md, icon.svg
```

On this machine `uv` comes from mise: `mise x uv@0.13.0 -- uv …`. For tests,
point `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and `XDG_CACHE_HOME` at a scratch
directory so Ross's real settings, model download and launcher entry are not
touched; the boot test writes the config it finds, so always run it with a
scratch config dir. Never `pkill -f savi_notes`: it matches the engine and
the shell running the command. Kill the window by PID (`hyprctl clients -j`).

A changed QML file needs a relaunch; nothing hot-reloads. Keyboard-drive the
window with `wtype`, but only while it has focus (Ross works on this machine;
check `hyprctl activewindow` first and abort otherwise), and screenshot the
window's own geometry with `grim -g`, never the full screen.

## Platform rules

- No Linux-only calls. Trash is `send2trash`, child processes get
  `NO_WINDOW` on Windows, the engine uses `pythonw.exe` there when present,
  paths are normalised to forward slashes before reaching QML, `Util.fileUrl`
  and `Markdown.js`'s `fileUrl` handle drive letters, `App.localPath`
  converts dialog URLs.
- Icons are Nerd Font glyphs (`String.fromCodePoint(0xf....)`). The app font
  is the system UI font with the bundled icon font behind it in the families
  list, so mixed text falls back; glyph-only `Text` items also set
  `font.family: Style.font.icon`. Whether the families fallback works on
  Windows/macOS is unverified; boxes instead of icons would mean every glyph
  `Text` needs the explicit family.
- Shortcut hints never hardcode "Ctrl": use `Style.ctrl` (Qt maps Control to
  Command on macOS, so bindings already work there).
- Meaning search is opt-in on first run, needs a `llama-server` (system one,
  else the pinned llama.cpp release build is downloaded) and the
  nomic-embed-text model; everything stays local. Word search works without.
- Mermaid diagrams render only when `mmdr` or `mmdc` (mermaid-cli) is on the
  PATH; otherwise the block shows as code. Math needs nothing.

## Keeping up with Wolfen Notes

Wolfen Notes is the upstream; Ross keeps improving it in `~/Work/wolfen-os`
and will later ask to bring the changes here. The tag `savi-notes-synced` in
that repo marks the last commit this port includes. To sync:

1. `git -C ~/Work/wolfen-os log --oneline savi-notes-synced..main -- shell/apps/notes`
   lists what's new; read each diff and apply it here by hand. Most QML is
   line-for-line the same; the mechanical differences are:
   - `import qs.Commons` / `import qs.Ui` → `import Savi`; no `import Quickshell`.
   - `Quickshell.env("HOME")` → `App.home`; `WOLFEN_PATH` has no equivalent.
   - `FloatingWindow` → `Window` with `visible: true`, `width`/`height`,
     `minimumWidth`/`minimumHeight`, `onClosing`; `IpcHandler` → `Connections
     { target: App }` (`onOpenRequested`); the engine `Process` → `Engine.qml`
     over `EngineBridge` (`engine.close()` instead of `stdinEnabled = false`).
   - `font.family: Style.font.family` lines are dropped (the app font is
     inherited) except glyph-only items (`Style.font.icon`) and the editor /
     code (`Style.font.mono`).
   - Strings containing `Ctrl` become `Style.ctrl + "…"`.
   - Dialog results go through `App.localPath(String(selectedFile))`.
   - The PDF op is `App.exportPdf(title, html, out)` in the host, not an
     engine op; `requestAssets` also passes `theme: Colors.diagram`.
   - `Colors.palette` entries are hex strings; `Markdown.js` converts them.
   - `notes-engine.py` → `engine.py`: see the `config`/`llama`/`mathsvg`
     imports, `send2trash`, `NO_WINDOW`, `SemanticOff`, the `settings` op, no
     `fork`/`prctl`/WeasyPrint/`gio`, and the final sync runs inline on EOF.
2. Things this port has that Wolfen doesn't: `Onboarding.qml`, the finder's
   Settings tab and `settingsRows`, the engine-restart handling in
   `Engine.qml`/`NotesWindow.qml`, the update dialog, `App.*` properties.
   Keep them when merging upstream edits to the same files.
3. Copy `FORMAT.md` over (retitle it "Savi Notes formatting") whenever
   Wolfen's changes, and bump the renderer together with it.
4. Move the marker: `git -C ~/Work/wolfen-os tag -f -a savi-notes-synced -m "…" && git -C ~/Work/wolfen-os push -f origin savi-notes-synced`.

## Releases and updates

Bump `version` in `pyproject.toml`, commit, push a tag `vX.Y.Z`. The release
workflow builds the wheel and publishes a GitHub release. The app reads the
latest release on launch; "Required update" in the release notes removes the
Later button. The update runs `uv tool install --force --reinstall
git+https://github.com/SaviPBC/savi-notes@vX.Y.Z` after the window closes
and reopens the app. `update.REPO` is the single place the repo name lives.

## Style

Match the code around you: two-space indentation in Python and QML, comments
that say why, no defensive checks around the package's own dependencies.
Ross is a minimalist: remove features completely rather than trimming them,
keep one obvious place for each thing (settings live in the finder's Settings
tab; per-note actions in This file), accent colour only on the selected or
active thing, and verify visual changes in the running app, not just by
reading the code.
