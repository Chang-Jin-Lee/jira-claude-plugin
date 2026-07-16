# jira-claude-plugin — Design

## Problem

Turning a whole Jira Kanban board into something an LLM-driven dev workflow
(superpowers: brainstorming → writing-plans → executing-plans) can act on is
manual today: open the board, click into every epic/story/subtask, copy
descriptions, write a spec, write a backlog by hand. `Jira_Automator`
(separate repo, already complete) solves the "crawl one issue tree" part via
a PowerShell script that takes a root issue key. This project wraps that idea
into a distributable Claude Code plugin that starts from a *board*, not a
single issue key, and carries the output through to a backlog and an
optional handoff into superpowers.

## Goals

- Given a Jira board (picked interactively or named up front), produce one
  consolidated Markdown document of the full issue tree under that board.
- From that document, produce a backlog document with per-item metadata
  (source issue, summary, dependencies, acceptance criteria).
- Offer (but never force) a handoff into the superpowers workflow.
- Ship as an installable Claude Code plugin (`/plugin marketplace add` +
  `/plugin install`), not just local `.claude/` config.
- Zero custom Jira REST client code — delegate all Jira access to the
  existing `sooperset/mcp-atlassian` MCP server.

## Non-goals

- Writing to Jira (creating/transitioning issues). Read-only.
- Building a new MCP server. We bundle and configure `mcp-atlassian`, we
  don't reimplement it.
- Automating all the way through code implementation without any user
  checkpoint. The plugin always stops and asks before continuing into
  superpowers.

## Architecture

- **Jira access**: entirely via the `mcp-atlassian` MCP server
  (https://github.com/sooperset/mcp-atlassian), run locally over stdio via
  `uvx mcp-atlassian`. The plugin does not call the Jira REST API directly.
- **Credentials**: collected via the plugin's `userConfig` (`jira_url`,
  `jira_email`, `jira_api_token` — the token marked `sensitive`). Claude Code
  prompts for these when the plugin is enabled and stores the token in the
  OS keychain / credentials store. No `.env` file, no plaintext token in the
  repo or in plugin files.
- **MCP bundling**: a `.mcp.json` at the plugin root declares the
  `mcp-atlassian` server, with its `env` sourced from
  `${user_config.jira_url}` / `${user_config.jira_email}` /
  `${user_config.jira_api_token}`.
- **Two entry points, one behavior**: a slash command
  (`/jira-to-backlog [board]`) for explicit invocation, and a Skill
  (`skills/jira-to-backlog/SKILL.md`) with a description that lets natural
  language ("이 지라 보드 문서화해줘") trigger the same flow. The command is a
  thin pointer at the same instructions the skill contains — no duplicated
  logic to keep in sync.
- **Distribution**: `.claude-plugin/marketplace.json` at the repo root lists
  this one plugin with `source: "./"`, so the same repo is both the plugin
  and its own marketplace — install via:
  ```
  /plugin marketplace add Chang-Jin-Lee/jira-claude-plugin
  /plugin install jira-to-backlog
  ```

## Workflow (skill/command instructions)

1. **Check Jira access.** Confirm Jira MCP tools are reachable. If not,
   point the user at plugin re-configuration (re-run `/plugin` to fill in
   `userConfig`, or check `uv`/`uvx` is installed).
2. **Resolve the board.** If no board name was given as an argument, query
   Jira for the boards/projects the user can see, list them numbered in the
   terminal, and ask the user to pick one. If a name was given, resolve it
   (exact match first, then fuzzy/substring; if ambiguous, show candidates
   and ask).
3. **Collect every issue on the board.** Not just epics — every issue
   visible on the board, paginated as needed.
4. **Recursively expand children.** For every issue collected, look up
   children (`parent = <key>`) not already visited, and recurse — same
   depth-first, visited-set approach `Export-JiraTree.ps1` already validates
   — until the whole tree under the board is captured. No node is processed
   twice.
5. **Write the consolidated document.** One Markdown file per board at
   `jira-docs/<BOARD-KEY>.md` in the user's current project (created if
   missing), one heading per issue (nesting mirrors parent/child depth),
   each recording: key, title, description, type, status, assignee,
   priority, and Jira URL.
6. **Generate the backlog.** From that document, `jira-docs/<BOARD-KEY>-backlog.md`:
   a flat, ordered list of backlog items, each with source issue key + link,
   one-line summary, any dependency this item has on another backlog item,
   and acceptance criteria pulled from (or inferred from) the issue
   description.
7. **Stop and ask before going further.** Never auto-continue into
   superpowers:
   - If the `superpowers` plugin/skills aren't available, offer to install
     them (`/plugin marketplace add obra/superpowers-marketplace` +
     `/plugin install superpowers`), then ask whether to continue.
   - If superpowers is available, ask whether to proceed into
     brainstorming/writing-plans using the generated backlog now, or stop
     here so the user can review the files first.

### Edge cases

- **Board not found / ambiguous name**: show close matches, ask the user to
  disambiguate rather than guessing.
- **Empty board**: report it, don't write empty output files.
- **Large boards** (many dozens/hundreds of issues): warn the user of the
  expected size before crawling and let them confirm, since this is a
  read-heavy operation against a rate-limited API.
- **Re-running on the same board**: overwrite the existing
  `jira-docs/<BOARD-KEY>*.md` files. No versioning/history — same behavior
  as `Export-JiraTree.ps1`.

## Repo layout

```
jira-claude-plugin/
├── .claude-plugin/
│   ├── plugin.json          # userConfig: jira_url, jira_email, jira_api_token
│   └── marketplace.json     # self-hosted marketplace entry
├── .mcp.json                 # bundles mcp-atlassian, env from ${user_config.*}
├── skills/
│   └── jira-to-backlog/
│       └── SKILL.md          # the workflow above
├── commands/
│   └── jira-to-backlog.md    # slash command, points at the same workflow
├── README.md                  # product-facing: what/why/how to use
├── LICENSE                    # MIT
└── .gitignore
```

## README approach

Product-facing only: what it does, why it exists, requirements (Claude Code,
a Jira Cloud account + API token, `uv`/`uvx` installed), install steps
(`/plugin marketplace add` + `/plugin install`), usage (`/jira-to-backlog`,
or just asking in natural language), and an example of what comes out of it.
No internal prompt/workflow details, no architecture diagrams — those live
in this spec and in `SKILL.md`, not in the README.

## Out of scope for this pass

- Confluence integration (mcp-atlassian supports it; we don't use it here).
- Any write-back to Jira.
- A dedicated MCP server of our own.
