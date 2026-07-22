# Codex CLI port — making the plugin installable outside Claude Code

## Problem

This plugin only works in Claude Code today: its manifest lives under
`.claude-plugin/`, its credential flow depends on Claude's `userConfig` →
`CLAUDE_PLUGIN_OPTION_*` env vars, and its `SessionStart` hook is wired
through Claude's `hooks/hooks.json` mechanism. The user wants to run the
same Jira-crawl skill from OpenAI's Codex CLI, which they use with the
`gpt-5.6-sol` model.

Codex CLI has its own, structurally similar plugin system
(`.codex-plugin/plugin.json`, `skills/`, `.mcp.json`), confirmed by reading
the `openai/codex` source directly (`codex-rs/core-plugins/src/manifest.rs`,
`codex-rs/config/src/hook_config.rs`) rather than assuming parity with
Claude Code. Two features this plugin currently depends on do not exist
there the same way:

- **No `userConfig` equivalent.** Codex's manifest schema
  (`RawPluginManifest` in `manifest.rs`) has no field for declaring
  user-supplied settings that get injected as env vars.
- **Plugin-bundled `hooks.json` is currently rejected by validation.**
  Confirmed via Codex's own bundled `plugin-creator` skill
  (`codex-rs/skills/src/assets/samples/plugin-creator/references/plugin-json-spec.md`):
  *"Validation rejects unsupported manifest fields such as `hooks`, so the
  scaffold keeps them out of generated manifests."*

`obra/superpowers` already ships working `.codex-plugin/` (and
`.cursor-plugin/`, `.kimi-plugin/`) manifests alongside its
`.claude-plugin/` one, in the same repo, sharing `skills/` and `scripts/`.
Its `.codex-plugin/plugin.json` sets `"hooks": {}` — it doesn't attempt a
Codex session hook at all, rather than forcing a workaround. This design
follows that same precedent: add Codex support in this repo, and for
anything Codex doesn't support the way Claude does, use Codex's own native
mechanism instead of simulating Claude's.

## Goals

- `codex plugin marketplace add <this-repo>` then `codex plugin add
  jira-claude-plugin@...` installs a working plugin: the `jira-to-backlog`
  skill is available, and the bundled `atlassian` MCP server connects with
  real Jira credentials.
- The standalone tree browser (`scripts/browse_tree.py`) works the same way
  for a Codex-only user (no Claude Code ever installed on that machine) as
  it does today for a Claude Code user.
- One shared `skills/jira-to-backlog/SKILL.md` continues to serve every
  harness. Its wording no longer hardcodes Claude-only commands
  (`/plugin`, `/plugin marketplace add obra/superpowers-marketplace`).
- Claude Code's existing behavior is unchanged: same hook, same
  `userConfig` prompts, same `run_mcp.py` wrapper.

## Non-goals

- No attempt to give Codex a session-start credential sync equivalent to
  Claude's hook. Codex's manifest validation currently rejects bundled
  hooks; this design does not fight that.
- No support for other harnesses superpowers also ships (Cursor, Kimi,
  OpenCode, Pi). Only Claude Code (existing) and Codex CLI (this design).
- No change to the crawl logic, doc/backlog output format, or the tree
  browser's REST/UI behavior — only how each harness discovers and
  configures the plugin.
- No renaming of the plugin (`jira-claude-plugin`) even though that name
  now undersells its Codex support — same precedent as superpowers keeping
  one `name` across all of its per-harness manifests. Revisit only if the
  user wants it later.

## Architecture

**Components:**

- **`.codex-plugin/plugin.json`** (new) — Codex's manifest, sibling to the
  existing `.claude-plugin/plugin.json`. Declares `"skills": "./skills/"`
  explicitly (matching superpowers' Codex manifest, even though it's also
  the default discovery path) and an **inline `mcpServers` object** (not a
  separate `.mcp.json` file — see Data flow below for why). No `hooks`
  field at all (superpowers uses `"hooks": {}`; this plugin omits the key
  entirely since it needs no Codex hook).
- **`.agents/plugins/marketplace.json`** (new) — the Codex-side
  marketplace entry, mirroring `obra/superpowers`'s file byte-for-byte in
  shape: `source: {"source": "url", "url": "./"}` (the whole repo root is
  the plugin, same as `.claude-plugin/marketplace.json`'s `"source": "./"`
  today).
- **`.mcp.json`** (existing, unchanged) — stays Claude-only. Still
  referenced implicitly by Claude's default component discovery, still
  points at `scripts/run_mcp.py` via `${CLAUDE_PLUGIN_ROOT}`.
- **`scripts/sync_credentials.py`** (small addition) — gains one shared
  function, `load_credentials(path)`, that both `run_mcp.py` and
  `browse_tree.py` will call instead of each doing their own file read:
  reads `~/.jira-claude-plugin/credentials.json` if it exists; if not,
  falls back to reading `JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN`
  directly from the process environment, returning `None` only if neither
  source has all three values. The Claude-only `main()` / hook entry point
  is untouched.
- **`scripts/browse_tree.py`** (small change) — swaps its current
  file-only `load_credentials()` for the new shared one, so a Codex-only
  user (who exported the three env vars themselves, per README) can run
  the browser without ever having a Claude Code session write the file.
- **`skills/jira-to-backlog/SKILL.md`** (wording only) — two edits:
  - Step 0 (prerequisites check): replace "run `/plugin` and fill in..."
    with harness-neutral guidance — point the user at this plugin's
    README for the exact steps for their tool (`/plugin` + `userConfig` on
    Claude Code; three exported env vars on Codex), rather than assuming
    Claude Code's flow.
  - Step 6 (superpowers handoff): replace the hardcoded
    `/plugin marketplace add obra/superpowers-marketplace` /
    `/plugin install superpowers` instructions with: ask whether to
    continue if a planning/brainstorming skill is already available in
    the session; if not, offer to install `obra/superpowers` using
    whichever install command matches the current harness (Claude Code:
    `/plugin marketplace add` + `/plugin install`; Codex CLI: `codex
    plugin marketplace add` + `codex plugin add` — superpowers ships a
    working `.codex-plugin/plugin.json`, confirmed by reading that repo).
- **`README.md`** — new "Install on Codex CLI" section: the two `codex
  plugin` commands, and instructions to export `JIRA_URL` / `JIRA_USERNAME`
  / `JIRA_API_TOKEN` (env-var names matching exactly what `mcp-atlassian`
  itself expects, so no remapping layer is needed anywhere) before first
  use, since Codex has no masked-secret-prompt equivalent to Claude's
  `userConfig` UI.

**Data flow — Codex MCP connection (why inline `mcpServers`, not a second `.mcp.json` file):**

Codex's plugin manifest docs state that a declared `skills` / `hooks` /
string-valued `mcpServers` path is *"supplemented on top of default
component discovery; they do not replace defaults."* The existing root
`.mcp.json` is already discoverable by that default convention and
contains Claude's `${CLAUDE_PLUGIN_ROOT}`-based wrapper command, which
Codex would not expand. To avoid Codex loading that broken entry
alongside a correct one, `.codex-plugin/plugin.json` declares its
`atlassian` server as an **inline object** directly in the manifest:

```json
"mcpServers": {
  "atlassian": {
    "command": "uvx",
    "args": ["mcp-atlassian"],
    "env": {
      "JIRA_URL": "${JIRA_URL}",
      "JIRA_USERNAME": "${JIRA_USERNAME}",
      "JIRA_API_TOKEN": "${JIRA_API_TOKEN}",
      "READ_ONLY_MODE": "true"
    }
  }
}
```

This needs no `run_mcp.py` wrapper and no plugin-root path resolution —
`uvx` is a bare executable, and Codex's documented `${VAR}` substitution
reads directly from the process environment. **Open risk:** whether Codex
still also auto-discovers the root `.mcp.json` regardless of the inline
declaration is not fully confirmed from documentation alone; the
implementation plan's first task must install the plugin locally with a
real Codex CLI and confirm only the intended `atlassian` server loads
(see Testing).

**Data flow — standalone tree browser, Codex-only user:**

1. User exports `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` in their
   shell profile once (README-documented, no plugin/hook involved).
2. User runs `uv run --with textual,requests scripts/browse_tree.py`
   directly, same command as today.
3. `browse_tree.py` calls the shared `load_credentials()`; the
   `~/.jira-claude-plugin/credentials.json` file doesn't exist on a
   Codex-only machine, so it falls back to the three env vars.
4. Browsing, selection, and clipboard copy behave identically to the
   existing Claude Code flow — nothing else in `browse_tree.py` changes.

**Data flow — skill handoff, either harness:**

Unchanged except step 0 and step 6's wording (see Components above); the
crawl, doc-writing, and backlog-writing steps (1-5) are harness-agnostic
already (they only call Jira MCP tools and write files) and need no
changes.

## Edge cases

- **Codex user has never set the three env vars**: the `atlassian` MCP
  server starts with empty/missing env values and `mcp-atlassian` itself
  will fail to authenticate — same failure the skill's step 0 already
  handles ("tell the user Jira isn't reachable yet... confirm
  configuration"), just pointed at env vars instead of `/plugin` for this
  harness.
- **Machine has both Claude Code and Codex CLI installed, Claude's hook
  already wrote `~/.jira-claude-plugin/credentials.json`**: Codex's
  `browse_tree.py` run picks up that file via the shared
  `load_credentials()` (file takes priority over env vars) with zero
  extra setup — a deliberate nice-to-have, not a requirement.
- **Root `.mcp.json` also gets auto-discovered by Codex** (the open risk
  above): if confirmed during implementation, resolve by whatever Codex's
  actual behavior demands — e.g. renaming/relocating the file so Codex's
  default discovery no longer finds it there, without breaking Claude's
  discovery of it. Do not guess further; verify live and adjust.
- **`load_credentials()` finds a file that's missing one of the three
  keys** (shouldn't happen given how the file is written, but the
  function should not partially trust it): treat as "no file", fall
  through to the env-var path, same as a missing file.

## Testing

- `scripts/tests/test_sync_credentials.py` gains cases for the new
  `load_credentials()`: file present and complete (used as-is, env
  ignored), file absent + all three env vars present (env used), file
  absent + env incomplete (returns `None`), file present but incomplete
  (falls through to env, per the edge case above).
- `scripts/tests/test_browse_tree_data.py` / existing browse-tree tests:
  no change needed beyond swapping which `load_credentials` is under test,
  since the REST-calling functions don't change.
- `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`
  aren't unit-testable (manifests, not code) — verify by actually running
  `codex plugin marketplace add`/`codex plugin add` against a real Codex
  CLI install and confirming: the `jira-to-backlog` skill is listed, the
  `atlassian` MCP server connects with env-var credentials, and the root
  `.mcp.json`-discovery risk above is resolved one way or the other. This
  plugin's own CI/sandbox does not have `codex` installed, so this step
  needs the user's machine.
- `SKILL.md` wording changes: not unit-testable — verify manually on both
  harnesses that step 0 and step 6 read correctly and point at commands
  that actually exist for that harness.

## Out of scope for this pass

- Cursor, Kimi, OpenCode, Pi, or any other harness superpowers supports.
- Any change to crawl/doc/backlog logic or the tree browser's UI/REST
  behavior.
- Automating Codex-side credential entry beyond documented manual env-var
  export (no interactive prompt equivalent exists to build against yet).
- Renaming the plugin.
