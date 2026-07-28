# Contributing

Thanks for taking a look at this project — bug reports, doc fixes, small
features, and big ideas are all genuinely welcome. This plugin started as a
one-person itch-scratch (Jira boards are tedious to read through by hand),
and it gets more useful the more real workflows it's tested against, so
don't hesitate to open an issue or PR even for something small.

## Ways to help

- **Report a bug** — open an issue with what you ran, what you expected,
  and what happened instead. If Claude Code printed an error, paste it in.
- **Suggest an idea** — new Jira fields to surface, a different backlog
  format, support for Jira Server/Data Center, non-Windows clipboard
  support for the tree browser — open an issue to discuss before writing
  code, so we don't build in the wrong direction.
- **Fix docs** — README typos, unclear setup steps, missing troubleshooting
  cases. These are small PRs and very welcome.
- **Submit a PR** — see the workflow below.

## Project layout

- `skills/jira-to-backlog/SKILL.md` — the crawler skill's instructions
  (prose, not code — this is what Claude actually follows)
- `scripts/browse_tree.py` — the standalone arrow-key tree browser (Textual)
- `scripts/sync_credentials.py` — the `SessionStart` hook that syncs Jira
  credentials to `~/.jira-claude-plugin/credentials.json`
- `scripts/run_mcp.py` — wrapper that launches the bundled Jira MCP server
  with credentials injected (from its own environment, or from the synced
  file as a fallback)
- `scripts/server_package.py` — keeps `mcp-atlassian` downloaded so the
  server can start from cache inside Claude Code's 30-second connect budget
- `scripts/bootstrap.sh`, `scripts/bootstrap.ps1` — install `uv` when it is
  missing, then start the server package downloading. Run by the skill, not
  by a hook (see the note on hook interpreters below)
- `scripts/mcp_recovery.py` — clears Claude Code's "needs authentication" flag
  for this plugin's server once the environment is healthy
- `scripts/tests/` — the test suite (pytest + pytest-asyncio)
- `hooks/hooks.json`, `.mcp.json`, `.claude-plugin/plugin.json` — Claude Code plugin wiring
- `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json` — Codex CLI plugin wiring (no hook; the `atlassian` MCP server reads `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN` from the environment directly)
- `docs/superpowers/` — design docs and implementation plans for past
  features, written with the [superpowers](https://github.com/obra/superpowers)
  skill pack; useful background reading, not required to contribute

## Getting set up

You only need [uv](https://docs.astral.sh/uv/) — nothing is installed
permanently. Run tests with:

```
uv run --no-project --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/ -v
```

There's no enforced linter yet, so tests are the real quality gate. New
behavior should come with a new or updated test in `scripts/tests/`.

## Things to watch out for

These are real constraints this plugin runs under — PRs that trip over
one of these are the most common source of rework, so please read before
diving in:

- **Read-only, always.** Never wire up a Jira call that writes, transitions,
  or creates an issue, even if the underlying MCP server or REST endpoint
  supports it. This plugin only ever reads.
- **The Jira API token must never be visible to the model or in any
  transcript.** Don't print it, log it, put it in a commit, or pass it as
  a bare CLI argument that could get echoed back.
- **Bump the version on every hook-affecting change.** If a PR touches
  `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.mcp.json`,
  `.codex-plugin/plugin.json`, or any file a hook depends on, bump
  `"version"` in all three manifests — `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json` — plus the
  version assertion in `scripts/tests/test_codex_plugin_manifest.py`. They
  must match. Otherwise `/plugin update` silently no-ops — installed users
  never see the fix.
  Keep `.codex-plugin/plugin.json`'s `"version"` in lockstep with those
  two as well, even though Codex has no equivalent update-skip failure
  mode — it's simpler to keep one version number across every manifest.
- **Don't add an explicit `"hooks"` field to `plugin.json`.**
  `hooks/hooks.json` at the plugin root auto-discovers; adding the field
  explicitly causes a "duplicate hooks file detected" load error.
- **The credentials sync path is fixed and home-relative** —
  `~/.jira-claude-plugin/credentials.json`, deliberately outside the
  plugin's own versioned install directory, so it survives plugin updates.
  Don't move it under the plugin folder.
- **That file is read by processes that start concurrently with the hook
  that writes it.** Write it only through `sync_credentials.write_credentials`
  (temp file + `os.replace`, skipped when unchanged) and read it only through
  `read_credentials` (returns `None` for absent, partial, or mid-write
  content). A plain `write_text`/`json.loads` pair on this path is a torn-read
  bug: the Jira MCP server crashes, Claude Code marks it as needing
  authentication, and the user gets asked to re-enter credentials that were
  never wrong.
- **Credentials should reach the MCP server through its `env` block**
  (`${user_config.*}` in `.mcp.json`), not through the file. The file is a
  fallback for older Claude Code builds and the standalone browser.
- **Nothing on the MCP server's startup path may touch the network.** Claude
  Code kills a server that hasn't connected in 30 seconds, and a `uvx`
  index resolve can turn into a ~150 MB download — which is why the server
  launches with `uvx --offline` and downloading belongs to the SessionStart
  hook. A SessionStart hook can't cover for it either: hooks start about
  150ms *after* the MCP server and run concurrently with it, so they cannot
  warm anything up in time for their own session.
- **No permanent installs.** Both scripts run via `uv run --with <deps>`,
  never `pip install`. Keep new scripts in that style.
- **Always pass `--no-project` to `uv run`.** These scripts run with the
  user's own project as the working directory; without it, `uv` tries to
  resolve and build *their* project first — creating a stray `.venv/` in
  their repo, or failing outright and taking the hook or MCP server down
  with it.
- **A failed MCP server stays failed across restarts.** Claude Code records it
  in `~/.claude/mcp-needs-auth-cache.json` and then skips starting it in later
  sessions, so a single early failure (no `uv`, cold package cache) means the
  user must reconnect by hand forever after — restarting never helps. That is
  what `scripts/mcp_recovery.py` exists to undo. Any change that can make the
  server fail to start needs to leave a path back out of that state.
- **Never add a hook that names a platform-specific interpreter.** A hook
  whose command isn't installed fails loudly on *every* session
  (`Executable not found in $PATH: "sh"`), and Claude Code has no way to
  scope a hook to one platform. An `sh` hook shipped in 0.1.11 and broke
  every Windows machine without Git Bash; `powershell` would break macOS and
  Linux identically. `hooks/hooks.json` may name only `uv`, and
  `scripts/tests/test_hooks_manifest.py` enforces that. Anything needing a
  shell belongs in the skill, which picks per platform at runtime.
- **The bootstrap scripts may not assume anything is on PATH** — not `uv`,
  not even `uname`. They run before the plugin's dependencies exist, so
  platform detection goes through environment variables, and note that
  Windows upper-cases env names (`SYSTEMROOT`, not `SystemRoot`) while a
  shell does not. Keep `bootstrap.sh` POSIX `sh`, and keep the two in step:
  the skill promises the same behaviour and the same
  `JIRA_PLUGIN_NO_BOOTSTRAP` / `JIRA_PLUGIN_UV_INSTALLER` knobs on both.
- **`bootstrap.ps1` must keep its UTF-8 BOM.** Windows PowerShell 5.1 decodes
  a BOM-less `.ps1` with the system ANSI codepage, turning its Korean output
  into mojibake. This is the PowerShell equivalent of the `reconfigure`
  gotcha below, and a test guards it.
- **Korean (and other non-ASCII) stdout on Windows needs**
  `sys.stdout.reconfigure(encoding="utf-8")` as the first statement of
  `main()` — otherwise it mangles into mojibake under the default system
  codepage.
- **Validate before committing:** `claude plugin validate .` should print
  `✔ Validation passed`.

## Workflow

- Fork the repo and branch off `master`.
- Keep PRs focused — one fix or feature per PR is much easier to review.
- Include or update tests for any behavior change.
- Run `claude plugin validate .` and the test suite before opening the PR.
- Describe *why* the change is needed, not just what it does — that's the
  part that's hard to recover from a diff alone.

For anything bigger than a small fix, opening an issue first to talk
through the approach saves everyone rework — happy to discuss design
before you write code.

## Reporting a security issue

If you find a way credentials or tokens could leak (logs, transcripts,
committed files), please open an issue marked clearly as security-sensitive
rather than including the actual leaked value, so it doesn't end up
public in the process of reporting it.
