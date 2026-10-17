# Savi Notes

Markdown notes organised by tags, with a finder (press Shift twice), search by
words and by meaning, side-by-side splits, a formatting toolbar, PDF export,
and a Claude Code skill so Claude can read and write your notes for you.
Notes are plain `.md` files in a folder you choose; nothing leaves your
computer.

Runs on Windows, macOS and Linux.

## Install

Paste this into Claude Code:

> Install Savi Notes: install `uv` if it's missing (https://docs.astral.sh/uv/getting-started/installation/),
> run `uv tool install git+https://github.com/SaviPBC/savi-notes`, then run `savi-notes`.
> The app asks where to keep notes on first launch and installs its Claude Code skill
> itself. When it's open, tell me how to find the app again and show me how the skill
> works by creating a note titled "Hello" with a couple of lines in it.

Or by hand:

```sh
uv tool install git+https://github.com/SaviPBC/savi-notes
savi-notes
```

The first launch asks for the notes folder, the theme and whether to search
by meaning, then adds the app to the Start Menu (Windows), `~/Applications`
(macOS) or the app launcher (Linux), and installs the Claude Code skill at
`~/.claude/skills/savi-notes`.

## Using it

- **Shift twice** opens the finder: notes (newest first, or type to search or
  create), tags, settings, and, with a note open, the actions for that note.
- **Click the note** or press **Ctrl+E** (⌘E on a Mac) to edit; **Esc** or the
  save button goes back to reading. Edits save as you type.
- The toolbar and **Insert** menu cover everything the renderer understands:
  `savi-notes format` prints the full list.
- Settings live in the finder's **Settings** tab: theme, meaning search, git
  sync, the notes folder, and checking for updates.

Claude Code picks up the skill on its next start. Then "put this in a note",
"find my note about X" or "check my notes" just work; `savi-notes search`,
`savi-notes tags`, `savi-notes format` and `savi-notes check` are what it
runs underneath.

## Updates

The app checks GitHub's latest release when it opens and offers to update
and reopen. `savi-notes update` does the same from a terminal. The Claude
Code skill ships inside the app, so updating the app updates the skill.

To publish a release: bump `version` in `pyproject.toml`, commit, and push a
tag like `v0.2.0`. The release workflow builds the wheel and publishes the
release; write "Required update" in the release notes to make the dialog
insist.

## Meaning search

With meaning search on, the first run downloads a small embedding model
(nomic-embed-text, about 150 MB) and, where no `llama-server` is installed, a
build of llama.cpp for your machine. Both run locally. Turn it off in
Settings to search by words only.

## Development

```sh
uv sync
uv run savi-notes
uv run python scripts/boot_test.py   # what CI runs on every platform
```

The window is Qt Quick (PySide6) hosting the QML under `src/savi_notes/qml`;
`engine.py` does the file work, search and git sync as a child process;
`FORMAT.md` documents the markdown the renderer (`Markdown.js`) supports and
is kept in step with it.
