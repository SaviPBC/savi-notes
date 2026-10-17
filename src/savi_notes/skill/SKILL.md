---
name: savi-notes
description: The user's notes, kept in Savi Notes. Use whenever the user asks to write, save, put or log something "to a note", "in my notes" or "in Savi Notes"; to find, read or update one of their notes; to list their tags; or to "check my notes".
---

# Savi Notes

The user's notes are markdown files in one folder, the vault; `savi-notes vault`
prints its path. They read and write them in the Savi Notes app, which
organises notes by **tags, not folders**, and picks up edits made on disk
while it is open. "A note" with no other place named always means a note here.

The `savi-notes` command works the same in a Unix shell and in PowerShell.

## Layout

- Every note is a `.md` file in the vault root, named by its title. There are
  no folders for notes; don't create any.
- Images, PDFs and other files live in `Attachments/` and are embedded with
  `![[file name.png]]`, which resolves by file name.
- Tags go in frontmatter, `tags: [work, planning]`, lowercase, words joined
  with `-`. `#tags` written in the text count too. Notes may carry other keys
  (`created`, `status`, `ticket`); keep them.

## Finding notes

`savi-notes search "<question or words>"` ranks notes by title, words and
meaning (local embeddings), one per line: `path<TAB>match<TAB>snippet`, where
match is `title`, `text` or `meaning`. Ask it in plain language ("how did we
fix the login redirect") as well as by keyword, then read the file.

For exact strings or regexes, grep the `*.md` files in the vault directly.
`savi-notes tags` lists every tag with how many notes carry it.

## Writing notes

Edit the files directly with the normal file tools; the app picks up changes
on disk. Rules:

- File name = title, in title case, e.g. `AI Gateway - HubSpot Migration.md`.
  Don't repeat the title as a `# H1`; start with content or `##` sections.
  Never create `Untitled*.md`, and check the name is free first.
- New notes get frontmatter:
  ```
  ---
  tags: [work, planning]
  created: YYYY-MM-DD
  ---
  ```
- Formatting: before writing anything beyond plain paragraphs, lists and
  links, run `savi-notes format`. It prints every syntax the app renders
  (callouts, embeds, block IDs, footnotes, math, diagrams, highlights,
  comments, tables, …) and is updated with the app, so use only what it
  lists. Link related notes with `[[Note name]]`; links make search and
  backlinks more useful.
- Tags: prefer one the user already uses (`savi-notes tags`); add a new one
  only when nothing fits, and say so.
- Renaming: rename the file, then update `[[Old name]]` and `[[Old name|...]]`
  links in other notes.
- Deleting: only when the user asks, and to the trash rather than `rm`.
- Daily notes are titled `MM-DD-YY` and tagged `daily`; "today's note" means
  that note, created if it doesn't exist.
- Before creating a note, search for the topic and offer to update an
  existing note instead of duplicating.
- After writing, tell the user the note's title.

## Sensitive content

Notes may hold credentials, API keys and personal data. Read them only when
the task needs them, never echo secrets back in chat or copy them into other
notes or files, and never put new secrets in a note unless the user asks.
Keys belong only in notes tagged `credentials` or `security`; if the user
asks to save one elsewhere, put it there and say why.

## Vault check ("check my notes")

Run `savi-notes check`. It is read-only and reports Untitled notes, notes
outside the vault root, media outside `Attachments/`, untagged and `inbox`
notes, key-shaped strings outside credential notes, links to notes that don't
exist and, for a git vault, its state. Summarize what it found and offer to
fix it.

## Syncing

If the vault is a git repository with a remote, the app commits, pulls and
pushes by itself while it is open, and stops without touching anything when a
pull conflicts. To sync by hand, run in the vault: `git add -A`, `git commit`,
`git pull --rebase`, `git push`. On a rebase conflict, read both sides of each
note and merge so no text from either is lost; keep both versions under a
short "Conflict: from <side>" marker when they can't be reconciled, and tell
the user. Never force-push, never `git reset --hard`, never drop a commit to
get past a conflict.
