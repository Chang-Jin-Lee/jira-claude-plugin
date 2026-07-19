# Interactive board/issue tree browser — Standalone-command redesign

## Relationship to the prior design

Supersedes the launch mechanism in
`docs/superpowers/specs/2026-07-16-interactive-board-browser-design.md`.
That design's feasibility spike
(`docs/superpowers/plans/2026-07-16-tty-passthrough-spike.md`) proved the
go/no-go gate FAILS: a `UserPromptExpansion` hook process gets neither an
inherited TTY nor direct `CON` access on this platform
(`stdin/stdout/stderr.isatty=False`, `CON_open_ok=False`, error `"File or
stream is not seekable."`). A hook can never host the arrow-key TUI itself.
This document keeps the prior design's goal (arrow-key tree browsing to
pick a board/issue) but changes the launch mechanism entirely: the TUI
runs as a fully standalone program the user launches directly from their
own shell, never as a hook child process. Everything below is
self-contained; the prior design's Architecture/Data-flow sections are
superseded, not extended.

## Problem

The current `jira-to-backlog` skill resolves a board by printing a static
numbered list and asking the user to type a number or key. There's no way
to see or pick a specific issue inside a board without already knowing its
key. The user wants a real, arrow-key-driven expand/collapse tree — press
right on a board to reveal its issues indented below, press left to
collapse, Enter to pick a node.

Genuine arrow-key interactivity requires a real, attached terminal. The
spike proved Claude Code's hook mechanism cannot provide one. So
interactive browsing and the Claude conversation must be two separate
programs: the browsing happens in a real terminal the user runs directly;
only the result (one resolved key) crosses back into the conversation.

## Goals

- Running one documented command directly in any terminal (not through
  Claude Code, not through a hook) opens a real interactive tree: boards
  at the top level, expandable with the right arrow, collapsible with the
  left arrow, navigable with up/down, confirmable with Enter.
- On Enter, the resolved key (board or issue) is copied to the OS
  clipboard and the program exits — the user switches back to Claude Code
  and pastes it in.
- Selecting a board behaves like today: the whole board gets crawled into
  a doc + backlog.
- Selecting a specific issue sets that issue as the crawl root instead —
  a single-issue document/backlog. **This does not exist in the skill
  today** (see Architecture) and is added as part of this design.
- Tree expansion is genuinely lazy: opening a board fetches only that
  board's issues at that moment; opening an issue fetches only its direct
  children at that moment.
- The Jira API token never becomes visible to the model (not in skill
  text, not typed into a Bash command, not in any transcript) and the
  user never has to re-type credentials already entered via `/plugin`.

## Non-goals

- No change to what happens once a root is resolved beyond the new
  single-issue path — the rest of the existing `jira-to-backlog` skill
  (collect issues, recurse, write doc, write backlog, ask about
  superpowers) is unchanged and reused as-is.
- No tree browser for natural-language invocation. Asking in natural
  language ("지라 KAN 보드 문서화해줘") still gets today's static
  numbered-list flow.
- No write access. The browser is read-only, same as the rest of the
  plugin.
- No caching/persistence of fetched tree data between runs.
- No packaging as a separately-distributed CLI (`uvx --from git+...`,
  PyPI, etc.) — the script is launched from the plugin's own install
  path, announced fresh each session. Revisit only if the plugin-path
  approach proves too brittle in practice.
- No cross-platform clipboard support. Like the TTY spike before it, this
  pass targets Windows only (the platform this plugin has been developed
  and tested on to date) — clipboard copy uses `clip.exe` directly.
  macOS/Linux support (`pbcopy`/`xclip`) is future work if the plugin
  ever targets those platforms.

## Architecture

**A deliberate, scoped exception to "zero custom Jira REST client code":**
the rest of the plugin still delegates 100% of Jira access to the bundled
`mcp-atlassian` MCP server. This one component — the interactive browser —
talks to the Jira REST API directly, with its own minimal HTTP client, because
it needs true lazy, on-keypress fetching that isn't possible through MCP tool
calls mediated by model turns. This exception is confined to
`scripts/browse_tree.py`; nothing else in the plugin gains direct REST access.

**Components:**

- **`scripts/sync_credentials.py`** — run once per Claude Code session by a
  `SessionStart` hook (no matcher; fires for every session where this
  plugin is active). Reads `CLAUDE_PLUGIN_OPTION_JIRA_URL` /
  `_JIRA_EMAIL` / `_JIRA_API_TOKEN` from its environment (the same
  mechanism confirmed working for hook processes during the TTY spike)
  and writes them as JSON to `~/.jira-claude-plugin/credentials.json` —
  a fixed, home-relative path, deliberately *not* under the plugin's
  versioned install directory, so it survives plugin updates. If any of
  the three values is empty (setup incomplete), it does not write the
  file and instead emits a plain-text reminder to run `/plugin` first.
  On success, it also emits (plain stdout text, matching
  `UserPromptExpansion`'s confirmed output contract, which the spike
  confirmed `SessionStart` shares): a one-line reminder of the exact
  command to launch the browser, with `${CLAUDE_PLUGIN_ROOT}` already
  substituted to a real path by the hook's own execution environment:
  `uv run --with textual,requests "<resolved path>/scripts/browse_tree.py"`.
  The internal split between "compute the credential dict" and "write
  the file" is a plain function boundary so the logic is unit-testable
  without real environment variables or disk I/O in the test.
- **`scripts/browse_tree.py`** — a standalone terminal program, launched
  directly by the user from their own shell (never by Claude Code, never
  by a hook), built with [`textual`](https://textual.textualize.io/)'s
  `Tree` widget (arrow-key expand/collapse/navigate and Enter-to-select
  are built into that widget). Run via `uv run --with textual,requests
  scripts/browse_tree.py` — no permanent install.
  - On start: reads `~/.jira-claude-plugin/credentials.json`. If missing,
    prints "Start a Claude Code session with this plugin active first,
    then try again" and exits non-zero — no Jira call is attempted.
  - Otherwise, calls Jira's agile-boards REST endpoint directly and
    renders each board as a top-level (collapsed) tree node.
  - On expanding a board node: fetches that board's issues (one REST
    call) and adds them as children, collapsed.
  - On expanding an issue node: fetches that issue's children via
    `parent = <key>` JQL (one REST call) and adds them, collapsed. A node
    with no children found renders as a leaf (no expand arrow).
  - On Enter: copies the selected node's key to the OS clipboard (Windows:
    `clip.exe` via subprocess — this plugin's supported platform per the
    existing plugin constraints), prints a one-line confirmation
    (`Copied <KEY> to clipboard — paste it into Claude Code.`), and exits 0.
  - On Ctrl-C/Esc without a selection: exits non-zero, clipboard
    untouched.
  - The REST-calling functions (list boards, list board issues, list
    issue children) are separated from the `textual` widget code so they
    can be unit-tested with mocked HTTP responses independent of the TUI.
- **`hooks/hooks.json`** — replaces the TTY-spike's diagnostic
  `UserPromptExpansion` entries entirely with a single `SessionStart`
  entry running `scripts/sync_credentials.py`.
- **`.claude-plugin/plugin.json`** — keeps the existing
  `"hooks": "./hooks/hooks.json"` field added during the spike (hooks do
  not auto-discover; this is required for any hook, including this one,
  to actually be wired up — confirmed the hard way during the spike).
- **`skills/jira-to-backlog/SKILL.md`** — step 1 gains issue-key
  detection: if the given text matches an issue-key pattern (project
  prefix + dash + number, e.g. `KAN-248`) rather than a bare project
  key/name, resolve it as a single issue via `jira_get_issue` and treat
  it as the crawl root — skip step 2's board-wide JQL entirely and start
  step 3's recursive child expansion from that one issue. The written
  document/backlog filenames use the issue key instead of a board key
  (e.g. `jira-docs/KAN-248.md`). All later steps (4-6) are otherwise
  unchanged. If the same text could plausibly be either an issue key or a
  literal board name, issue-key pattern match wins (issue keys are
  syntactically distinctive: letters + dash + digits).

**Data flow — credential sync (every session start):**

1. User starts a Claude Code session with this plugin active.
2. `SessionStart` fires `sync_credentials.py`.
3. If `/plugin` setup is complete, it writes
   `~/.jira-claude-plugin/credentials.json` and announces the browse
   command as context; if not, it announces the setup reminder instead
   and writes nothing.

**Data flow — browsing and handoff (whenever the user wants to browse):**

1. User runs the announced command directly in any terminal — this
   process has no relationship to Claude Code at all once launched.
2. `browse_tree.py` reads the synced credentials file, hits Jira's REST
   API directly, renders the interactive tree.
3. User navigates and presses Enter on a board or issue.
4. The script copies that key to the clipboard and exits.
5. User switches back to the Claude Code conversation and pastes the key
   (optionally with the skill's slash command, e.g.
   `/jira-claude-plugin:jira-to-backlog KAN-248`, or just the bare key if
   asked to invoke the skill).
6. The skill's step 1 (now issue-key-aware) resolves it directly and
   proceeds exactly as today from there — board crawl or, if it's an
   issue key, the new single-issue crawl.

## Edge cases

- **Board/issue has zero children when expanded**: render as a leaf (no
  expand indicator), same as the existing skill's "empty" handling.
- **REST call fails mid-browse** (bad credentials, network, rate limit):
  show the error inline in the tree UI (a red status line), let the user
  retry or quit; quitting without a selection leaves the clipboard
  untouched.
- **Credentials file missing or stale** (plugin never configured, or
  configured after the file was last synced): `browse_tree.py` tells the
  user to start/restart a Claude Code session with the plugin active
  (which re-syncs on every `SessionStart`) rather than attempting a Jira
  call with bad/missing credentials.
- **User quits without selecting** (Ctrl-C / Esc): script exits
  non-zero, clipboard unchanged, nothing to paste — user simply doesn't
  paste anything and the conversation proceeds as if browsing never
  happened.
- **Very large board** (many issues at one level): a single REST page
  fetch per expand, not a full recursive crawl — cheaper than the
  existing "large board" full-crawl warning and needs no separate guard,
  but paginate if a single board page exceeds what the Jira endpoint
  returns in one call.
- **Pasted text matches neither a board nor an issue-key pattern**: step
  1's existing "nothing matches" fallback (list boards, ask the user to
  pick) applies unchanged.

## Testing

- `sync_credentials.py`: unit tests around the pure "env vars in → config
  dict out" function (complete/incomplete env vars) and a separate check
  that the file-write step targets the fixed home-relative path — no real
  environment or Claude Code session needed.
- `browse_tree.py`: unit tests for the three REST-calling functions
  (list boards / list board issues / list issue children) against mocked
  HTTP responses, independent of the TUI. `textual` apps support a
  headless test mode (`Pilot` / `run_test()`) that simulates key input
  without a real terminal — use it to test arrow-key expand/collapse and
  Enter-to-select against a fake tree; mock the clipboard call in these
  tests.
- `SKILL.md` issue-key detection: not unit-testable (it's a prompt, not
  code) — verify manually during implementation by pasting an issue key
  and confirming the single-issue crawl path is taken, reusing the
  existing manual `KAN-248` test as the reference case.
- `SessionStart` hook itself: given how many wrong assumptions the TTY
  spike surfaced about hook behavior, the implementation plan's first
  task must include one live, human-triggered check that `SessionStart`
  actually fires every session and writes the credentials file — before
  building the rest of `browse_tree.py` on top of that assumption.

## Out of scope for this pass

- Natural-language-triggered interactive browsing (see Non-goals).
- Any richer navigation than expand/collapse/select (no search/filter
  box, no multi-select).
- Reusing this REST client anywhere else in the plugin.
- Packaging the browser as an installable CLI independent of the plugin.

## Implementation verification

Verified live on 2026-07-19 against the installed 0.1.6 cache with real
Jira credentials, driving the actual `BrowseApp` via Textual's Pilot
(headless driver — same app code, bindings, REST calls, and clipboard
path a user hits from their terminal):

- Boards loaded on mount (1 board: `KAN — KAN board`).
- Right-arrow on the board node lazily fetched and expanded its issues
  (242 issues via the v3 `/search/jql` endpoint — pagination confirmed
  live). Left-arrow collapsed it. (Arrow-key bindings were added in
  0.1.6 after live testing found Textual's `Tree` only binds Space.)
- Enter on an issue exited the app returning `KAN-258`, and the real
  Windows clipboard contained `KAN-258` (verified via `Get-Clipboard`).
- Pasting the key into the skill: `SKILL.md`'s issue-key detection
  correctly routed `KAN-258` to the single-issue path (board fetch
  skipped). The crawl itself was blocked by a Claude Code bug —
  `${user_config.*}` in a plugin `.mcp.json` `env` block is never
  interpolated (anthropics/claude-code#51573), so the bundled
  mcp-atlassian server had no credentials. Fixed in 0.1.7 by launching
  the server through `scripts/run_mcp.py`, which injects credentials
  from the hook-synced `~/.jira-claude-plugin/credentials.json`;
  verified live via a direct MCP stdio handshake + `jira_get_issue`
  call returning real KAN-258 data. Full in-session skill crawl still
  pending one plugin update + session restart.
