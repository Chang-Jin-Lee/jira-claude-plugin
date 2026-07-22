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
  with credentials injected (works around a Claude Code env-interpolation bug)
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
uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/ -v
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
  `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.mcp.json`, or any
  file a hook depends on, bump `"version"` in both `.claude-plugin/plugin.json`
  and `.claude-plugin/marketplace.json` (they must match). Otherwise
  `/plugin update` silently no-ops — installed users never see the fix.
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
- **No permanent installs.** Both scripts run via `uv run --with <deps>`,
  never `pip install`. Keep new scripts in that style.
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
