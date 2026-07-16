# Interactive board/issue tree browser — Design

## Problem

The current `jira-to-backlog` skill resolves a board by printing a static
numbered list ("1) KAN — ...", "2) APP — ...") and asking the user to type a
number or key. Real usage (testing against a live Jira site,
`metropia1.atlassian.net`) showed this is workable but flat: there's no way
to see or pick a specific issue inside a board without already knowing its
key. The user wants a real, arrow-key-driven expand/collapse tree — press
right on a board to reveal its issues indented below, press left to
collapse, Enter to pick a node — the way a file tree explorer works.

This is not achievable inside the chat turn itself: Claude's responses are
message-based, not a live-redrawing terminal display, and Claude cannot
react to a raw keypress between messages. Delivering genuine arrow-key
interactivity requires a real, separate, keyboard-driven terminal program.

## Goals

- Typing `/jira-claude-plugin:jira-to-backlog` (with or without a board/issue
  argument) launches a real interactive terminal tree: boards at the top
  level, expandable with the right arrow to reveal their issues, collapsible
  with the left arrow, navigable with up/down, confirmable with Enter.
- Selecting a board root behaves like today: the whole board gets crawled
  into a doc + backlog.
- Selecting a specific issue node inside a board's tree sets that issue as
  the crawl root instead — a single-issue document/backlog, the way the
  companion `Export-JiraTree.ps1` project and our manual `KAN-248` test
  already worked, but reachable by browsing instead of typing a key.
- Tree expansion is genuinely lazy: opening a board fetches only that
  board's issues at that moment; opening an issue fetches only its direct
  children at that moment. No upfront "fetch every board's full tree"
  pass.
- The Jira API token never becomes visible to the model (not in skill
  text, not typed into a Bash command, not in any transcript).

## Non-goals

- No change to what happens once a root is resolved — steps 2-6 of the
  existing `jira-to-backlog` skill (collect issues, recurse, write doc,
  write backlog, ask about superpowers) are unchanged and reused as-is.
- No tree browser for natural-language invocation in this pass. Asking in
  natural language ("지라 KAN 보드 문서화해줘") still gets today's static
  numbered-list flow. Only the explicit slash invocation gets the new
  interactive tree. (The mechanism this design relies on —
  `UserPromptExpansion` — only fires for typed slash/skill invocations, not
  for the model deciding mid-conversation to use a skill.)
- No write access. The browser is read-only, same as the rest of the
  plugin.
- No caching/persistence of fetched tree data between runs.

## Architecture

**A deliberate, scoped exception to "zero custom Jira REST client code":**
the rest of the plugin still delegates 100% of Jira access to the bundled
`mcp-atlassian` MCP server. This one new component — the interactive
browser — talks to the Jira REST API directly, with its own minimal HTTP
client. It needs true lazy, on-keypress fetching, which isn't possible
through MCP tool calls mediated by model turns. This exception is confined
to `scripts/browse_tree.py`; nothing else in the plugin gains direct REST
access.

**Components:**

- `scripts/browse_tree.py` — a standalone terminal program built with
  [`textual`](https://textual.textualize.io/)'s `Tree` widget (arrow-key
  expand/collapse/navigate and Enter-to-select are built into that widget,
  not hand-rolled). Run via `uv run --with textual,requests
  scripts/browse_tree.py` — no permanent install, consistent with the
  plugin's existing hard requirement on `uv`.
  - On start: calls Jira's agile-boards REST endpoint directly and renders
    each board as a top-level (collapsed) tree node.
  - On expanding a board node: fetches that board's issues (one REST call)
    and adds them as children, collapsed.
  - On expanding an issue node: fetches that issue's children via
    `parent = <key>` JQL (one REST call) and adds them, collapsed. A node
    with no children found renders as a leaf (no expand arrow).
  - On Enter: prints the selected node's key as a single line to stdout
    and exits 0. Any other exit (Ctrl-C, error) exits non-zero and prints
    nothing, so the hook can tell "user picked something" apart from
    "user backed out."
- `hooks/hooks.json` — registers a `UserPromptExpansion` hook matched to
  this plugin's skill invocation (the exact matcher string — the skill's
  namespaced name as Claude Code expects it in a `UserPromptExpansion`
  matcher — is confirmed empirically during the feasibility spike below,
  since the reference docs describe the mechanism but not a worked example
  for a plugin skill name). The hook's `command` runs a small wrapper,
  `scripts/hook_expansion.py` (exec form, not shell form, so
  `${user_config.*}` substitution never touches a shell parser), which:
  1. execs `scripts/browse_tree.py` as a child process attached to the
     same TTY, and captures its stdout after it exits;
  2. if that child exited 0 with a key on stdout, prints
     `{"hookSpecificOutput": {"additionalContext": "The user selected
     <KEY> from the interactive browser — use it directly as the crawl
     root, do not ask which board again."}}` to its own stdout (exit 0);
  3. otherwise (non-zero exit / no key), prints nothing and exits 0, so
     the skill proceeds exactly as it does today (falls back to listing
     boards itself via MCP).
  The three Jira credentials reach this wrapper (and the browser it
  launches) via the `CLAUDE_PLUGIN_OPTION_JIRA_URL` / `_JIRA_EMAIL` /
  `_JIRA_API_TOKEN` environment variables Claude Code sets on the hook
  process — the same three `userConfig` values the MCP server already
  uses, now also reaching this hook, but never reaching the model.
- `skills/jira-to-backlog/SKILL.md` — step 1 gets one new paragraph: if
  `additionalContext` already states a resolved board/issue key (from the
  hook), use it directly and skip straight to step 2; otherwise (natural
  language invocation, or the hook found nothing), fall back to the
  existing MCP-based numbered-list behavior unchanged.

**Data flow for a slash invocation:**

1. User types `/jira-claude-plugin:jira-to-backlog` (with or without an
   argument).
2. Before the skill's prompt reaches the model, `UserPromptExpansion`
   fires `scripts/browse_tree.py` with the three credentials in its
   environment.
3. The script hits Jira's REST API directly, renders the interactive tree,
   the user navigates and presses Enter on a board or issue.
4. The script prints that key to stdout and exits 0.
5. The hook wraps that into `additionalContext` and the skill's prompt
   proceeds with that context already present.
6. The skill (unchanged from step 2 onward) crawls from that root via the
   existing MCP-based recursive logic, writes the doc + backlog, and asks
   about superpowers — identical to today.

## Feasibility spike (before full build)

Whether a `UserPromptExpansion` hook process actually gets the real,
attached TTY needed for arrow-key input (raw mode, escape sequences) is not
guaranteed by the documentation reviewed for this design. Before building
the full tree browser, build and manually verify a two-line spike: a
`textual` app that does nothing but print which arrow key was pressed, run
through the same hook mechanism end-to-end. If the spike can't read arrow
keys through the hook, this design needs to fall back to a different
launch mechanism (research escalates to the human at that point — this is
a go/no-go gate, not a detail to route around silently).

## Edge cases

- **Board/issue has zero children when expanded**: render as a leaf (no
  expand indicator), same as the existing skill's "empty" handling.
- **REST call fails mid-browse** (bad credentials, network, rate limit):
  show the error inline in the tree UI (a red status line), let the user
  retry or quit; quitting without a selection means the hook returns no
  `additionalContext` and the skill falls back to its existing behavior.
- **User quits without selecting** (Ctrl-C / Esc): script exits non-zero,
  no stdout, hook adds no context, skill proceeds as if the browser had
  never run.
- **Very large board** (many issues at one level): this is a single REST
  page fetch per expand, not a full recursive crawl, so this is far
  cheaper than the existing "large board" full-crawl warning and needs no
  separate guard — but paginate if a single board page exceeds what the
  Jira endpoint returns in one call.

## Out of scope for this pass

- Natural-language-triggered interactive browsing (see Non-goals).
- Any richer navigation than expand/collapse/select (no search/filter box,
  no multi-select).
- Reusing this REST client anywhere else in the plugin.
