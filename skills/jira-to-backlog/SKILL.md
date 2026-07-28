---
description: Crawl a Jira Kanban board into one consolidated document and a backlog, then optionally hand off to superpowers. Use when the user names a Jira board/project and asks to document it, summarize it, turn it into a backlog, or start work on it.
---

# Jira board → doc → backlog

## 0. Prerequisites check

This skill is strictly read-only: never call any Jira tool that writes,
transitions, or creates issues, even if the connected MCP server offers one.

Confirm Jira MCP tools are available (tools exposed by the `atlassian` MCP
server this plugin bundles, typically named like `jira_search` /
`jira_get_issue`).

If they are there, go straight to step 1. If none are visible, **fix the
setup yourself rather than handing the user a checklist** — this is the one
moment where the environment can actually be repaired, so do the work here.
Saved credentials are almost never the cause, so do not open by asking the
user to retype them.

Diagnose in this order and act on the first thing that is wrong.

**a. Is `uv` usable?** Run `uvx --version`.

If that fails, the plugin cannot run anything at all, so set it up now.
Tell the user what you are about to install, then run the bundled script for
their platform from `${CLAUDE_PLUGIN_ROOT}/scripts/`:

- Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap.ps1`
- macOS/Linux: `sh bootstrap.sh`

It installs uv with the official per-user installer (no administrator
rights), starts the ~150 MB Jira server package downloading in the
background, and clears the failed-server flag Claude Code will have recorded
when the server couldn't start earlier in this session. Relay what it prints.
Then **stop and tell the user to fully quit their terminal application — the
whole app, not just one window — and start Claude Code again from a new
terminal.** uv's installer edits the user PATH, and neither this session nor
a Claude Code relaunched from the same terminal can see that change, so there
is nothing further to try here. That one restart is all they should need.

**b. Is the server package downloaded?** Run
`uvx --offline mcp-atlassian --version`.

If that fails, it is still downloading, or was never fetched. Claude Code
only waits 30 seconds for a server to start, which a first-time ~150 MB
download does not fit inside. Run `uvx mcp-atlassian --version` and wait for
it to finish, then ask the user to reconnect `atlassian` from `/mcp`, or
start a new session.

**c. Is Jira configured?** Only now is this worth checking. In Claude Code,
`/plugin` shows whether `jira_url` / `jira_email` / `jira_api_token` are
populated; other harnesses use the `JIRA_URL` / `JIRA_USERNAME` /
`JIRA_API_TOKEN` environment variables. If they are genuinely empty, have
the user fill them in. If they are already set, re-entering them has never
been the fix.

**d. Everything above checks out.** The server failed to start for some other
reason, and a failed server stays down — not just for this session. Claude
Code records it and skips starting it in later sessions too, so restarting
alone will not bring it back. Ask the user to reconnect `atlassian` from
`/mcp` (opening and closing `/plugin` also reconnects). Note that Claude Code
may label it as needing authentication; this plugin uses no OAuth, so that
label only ever means "failed to start". The plugin's own SessionStart hook
clears that flag once the environment is healthy, so this should be a
one-time step. If it still will not come up, the server's log says why; on
Windows it is under
`%LOCALAPPDATA%\claude-cli-nodejs\Cache\<project>\mcp-logs-plugin-jira-claude-plugin-atlassian\`.

Stop after whichever step applies — do not continue into the crawl until
Jira tools are actually available.

## 1. Resolve the board or issue

If `$ARGUMENTS` (or the user's message) matches an issue-key pattern —
a project prefix followed by a dash and a number, e.g. `KAN-248` — treat
it as a single issue, not a board: fetch it directly with `jira_get_issue`
and use it as the crawl root for step 3 onward, **skipping step 2's
board-wide fetch entirely**. The written document/backlog filenames use
this issue key instead of a board key (e.g. `jira-docs/KAN-248.md`,
`jira-docs/KAN-248-backlog.md`).

Otherwise, if `$ARGUMENTS` (or the user's message) names a board/project,
try to resolve it directly — exact key or name match first. If nothing
was given, or nothing matches:

- Use the available Jira tools to list the boards/projects the
  authenticated user can see (for example, a JQL project search, or a
  dedicated "list boards" tool if the connected MCP server exposes one —
  check what's actually available rather than assuming a specific tool
  name).
- Print them as a numbered list in the terminal (key — name).
- Ask the user to pick one by number, or type the key/name directly.

If a name was given but matches more than one board, show the candidates
and ask which one instead of guessing.

## 2. Collect every issue on the board

Once a board is resolved, fetch **all** issues on it — not just epics —
using JQL scoped to that board/project (e.g. `project = <KEY>`, or the
board's own saved filter if one is exposed), paginating through results
until there are no more pages.

If this comes back with zero issues, tell the user the board appears
empty and stop here — do not create any `jira-docs/` files.

## 3. Recursively expand children

For every issue collected in step 2, look up its children with
`parent = <issue key>` and recurse into each child the same way. Keep a
visited-set of issue keys so no issue is fetched or processed twice — an
issue reachable both directly from the board and as someone else's child
should still appear only once in the final tree, under its actual parent.
Stop recursing once an issue key has already been visited.

For each issue, record: key, title/summary, full description, issue type,
status, assignee, priority, and its Jira URL (`<jira_url>/browse/<KEY>`).

## 4. Write the consolidated document

Save one Markdown file to `jira-docs/<ROOT-KEY>.md` in the user's current
project directory (create `jira-docs/` if it doesn't exist yet; overwrite
the file if it already exists — no versioning). Structure:

- One heading per issue, nested to match parent/child depth (top-level
  board issues at `##`, their children at `###`, and so on, capping heading
  depth at `######` for very deep trees).
- Under each heading: Type, Status, Assignee, Priority (if set), Jira link,
  then the full description (or "(No description)" if empty).

Before writing, if the board has more than roughly 150 issues total, tell
the user the count and ask them to confirm before continuing — this is a
read-heavy crawl against a rate-limited API and large boards take a while.

## 5. Generate the backlog

From the tree just captured, write `jira-docs/<ROOT-KEY>-backlog.md`: a
flat, ordered list of backlog items (ordered by the board's own issue
order, or by created-date ascending if that's not available). For each
item include:

- **Source**: issue key + Jira link
- **Summary**: one line, plain language — rewrite the raw Jira title if
  it's unclear on its own
- **Depends on**: other backlog item(s) this one needs first, if evident
  from the parent/child relationship or from description text referencing
  another issue key
- **Acceptance criteria**: pulled from the issue description if it already
  lists them; otherwise 2-4 bullet points inferred from the description of
  what "done" looks like for that item

Skip issues whose status is already Done/Closed/Resolved. Note at the top
of the backlog file how many were skipped and why.

## 6. Stop and ask before continuing

Do not continue into superpowers on your own. After writing both files,
tell the user where they were saved, then:

- If no `superpowers` skills are available in this session, ask whether
  they'd like to install that plugin now, using whichever command matches
  the tool this skill is running in (Claude Code: `/plugin marketplace add
  obra/superpowers-marketplace` then `/plugin install superpowers`; Codex
  CLI: `codex plugin marketplace add obra/superpowers-marketplace` then
  `codex plugin add superpowers@...`, using the marketplace name printed
  by that add command). If yes, walk them through it, then ask the
  question below. If no, stop here.
- If `superpowers` skills are available, ask whether to continue straight
  into brainstorming/writing-plans using `jira-docs/<ROOT-KEY>-backlog.md`
  as the input, or stop here so they can review the files first.

Only invoke a superpowers skill after the user explicitly says yes to that
question.
