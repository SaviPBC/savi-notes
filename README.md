# Savi Notes

Markdown notes organised by tags, with a finder (press Shift twice), search by
words and by meaning, side-by-side splits, a formatting toolbar, PDF export,
and a Claude Code skill so Claude can read and write your notes for you.

Sign in with your Savi Google account and your notes are on every computer
you use. They are encrypted on your computer before they're saved to the Savi
AI Core, under a key only you hold, so no one at Savi can read them.

Runs on Windows, macOS and Linux.

## Install

Paste this into Claude Code:

> Install Savi Notes: install `uv` if it's missing (https://docs.astral.sh/uv/getting-started/installation/),
> run `uv tool install git+https://github.com/SaviPBC/savi-notes`, then run `savi-notes`.
> The app asks me to sign in on first launch and installs its Claude Code skill
> itself. When it's open, tell me how to find the app again and show me how the skill
> works by creating a note titled "Hello" with a couple of lines in it.

Or by hand:

```sh
uv tool install git+https://github.com/SaviPBC/savi-notes
savi-notes
```

The first launch asks for the theme and whether to search by meaning, then
opens the browser to sign in to the Savi AI Core. On your first computer it
shows a **recovery key**: save it in your password manager, because it's what
unlocks your notes on your next computer, and Savi has no copy. Then it adds
the app to the Start Menu (Windows), `~/Applications` (macOS) or the app
launcher (Linux), and installs the Claude Code skill at
`~/.claude/skills/savi-notes`.

## Using it

- **Shift twice** opens the finder: notes (newest first, or type to search or
  create), tags, settings, and, with a note open, the actions for that note.
- **Click the note** or press **Ctrl+E** (⌘E on a Mac) to edit; **Esc** or the
  save button goes back to reading. Edits save as you type.
- The toolbar and **Insert** menu cover everything the renderer understands:
  `savi-notes format` prints the full list.
- If you edit internal articles for your department on the AI Core, the
  finder has an **Articles** tab: open one to read or edit it, and leaving the
  editor publishes it.
- Settings live in the finder's **Settings** tab: theme, meaning search,
  copying your recovery key, signing out, and checking for updates.

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

## How your notes are kept

- Each note and attachment is encrypted with AES-256-GCM on your computer
  before it's sent. The AI Core stores only that ciphertext, and never sees the
  key, so neither Savi nor anyone who got into the server can read a note.
- The key is made on your first computer and leaves it only as the recovery
  key you write down. Lose the recovery key and every computer you're signed
  in on, and the notes can't be recovered by anyone; the sign-in screen's
  "Start over" clears them so you can begin again.
- This computer keeps a plain copy (`savi-notes vault` prints where), which the
  editor, search and the Claude skill read, protected like the rest of your
  files. A note you ask Claude to read is sent to Anthropic like any prompt.
- When a note changed on two computers, the one that syncs second keeps its
  text and saves the other as "Title (conflict DATE)", so nothing is lost.

## Meaning search

With meaning search on, the first run downloads a small embedding model
(nomic-embed-text, about 150 MB) and, where no `llama-server` is installed, a
build of llama.cpp for your machine. Both run locally. Turn it off in
Settings to search by words only.

## Development

```sh
uv sync
uv run savi-notes
uv run python scripts/sync_test.py   # two devices through a stand-in AI Core
uv run python scripts/boot_test.py   # what CI runs on every platform
```

The window is Qt Quick (PySide6) hosting the QML under `src/savi_notes/qml`;
`engine.py` does the file work and search as a child process, `sync.py` the
encrypted sync with the AI Core and `account.py` the sign-in;
`FORMAT.md` documents the markdown the renderer (`Markdown.js`) supports and
is kept in step with it.
