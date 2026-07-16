# jira-claude-plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an installable Claude Code plugin that crawls a Jira Kanban board (via the bundled `mcp-atlassian` MCP server) into one consolidated document, generates a backlog from it, and asks whether to hand off into the `superpowers` workflow.

**Architecture:** A single Skill (`skills/jira-to-backlog/SKILL.md`) holds all the workflow instructions and is reachable two ways — natural language (via its `description`) and an explicit `/jira-claude-plugin:jira-to-backlog [board]` invocation using `$ARGUMENTS` — there is no separate `commands/` file, since in Claude Code's plugin model a `skills/<name>/SKILL.md` already provides both invocation paths (confirmed against the plugin docs quickstart, which showed `$ARGUMENTS` working directly in a `skills/` skill). Jira access is delegated entirely to `mcp-atlassian`, bundled via `.mcp.json` and configured from the plugin's `userConfig` (prompted at install time, stored securely — no `.env`, no plaintext token in the repo). The plugin is distributed via a self-hosted `.claude-plugin/marketplace.json` so it can be installed with `/plugin marketplace add` + `/plugin install`.

**Tech Stack:** Claude Code plugin format (`.claude-plugin/plugin.json`, `.mcp.json`, `skills/`), Markdown + JSON only — no application code, no build step. Runtime Jira access via `uvx mcp-atlassian` (Python, installed by the end user, not by us).

## Global Constraints

- Repo: `https://github.com/Chang-Jin-Lee/jira-claude-plugin` (public), local path `C:\ChangJinGithub\jira_claude_plugin`, already `git init`'d with a first commit (`docs/superpowers/specs/2026-07-16-jira-claude-plugin-design.md`) pushed to `origin/master`.
- License: MIT, author `Chang-Jin-Lee`.
- No custom Jira REST client code — every Jira read goes through `mcp-atlassian` tools.
- Read-only: never write, transition, or create Jira issues.
- Never continue into `superpowers` without asking the user first (spec §Workflow step 6/7).
- Output docs go to `jira-docs/<BOARD-KEY>.md` and `jira-docs/<BOARD-KEY>-backlog.md` in the *user's* current project (not this repo) — `jira-docs/` is already `.gitignore`'d in this repo since it's just where the skill's own instructions say to write, not something this repo produces itself.
- Commit after every task (small, frequent commits — see each task's last step). Push at the end of each task that lands a working, `claude plugin validate`-clean state, and always at the very end.
- Local git identity for this repo only (already set): `user.name "Chang-Jin-Lee"`, `user.email "Chang-Jin-Lee@users.noreply.github.com"`.
- Verification tool: `claude plugin validate <path>` (available on this machine, `claude --version` reports `2.1.206`). Use `--strict` for the final check so unrecognized fields/missing metadata fail loudly.

---

### Task 1: Plugin manifest with userConfig

**Files:**
- Create: `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: nothing (first plugin file).
- Produces: the plugin's `name` (`jira-claude-plugin`) — this is the namespace prefix every later skill/marketplace file assumes (e.g. `/jira-claude-plugin:jira-to-backlog`). Produces three `userConfig` keys — `jira_url`, `jira_email`, `jira_api_token` — that Task 2's `.mcp.json` references as `${user_config.jira_url}` / `${user_config.jira_email}` / `${user_config.jira_api_token}`.

- [ ] **Step 1: Confirm there's nothing to validate yet**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: an error/failure noting no plugin manifest was found (there is no `.claude-plugin/plugin.json` yet).

- [ ] **Step 2: Create the plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "jira-claude-plugin",
  "description": "Crawl a Jira Kanban board into a document and backlog, then optionally hand off to superpowers to start the work.",
  "version": "0.1.0",
  "author": {
    "name": "Chang-Jin-Lee"
  },
  "homepage": "https://github.com/Chang-Jin-Lee/jira-claude-plugin",
  "repository": "https://github.com/Chang-Jin-Lee/jira-claude-plugin",
  "license": "MIT",
  "keywords": ["jira", "kanban", "backlog", "atlassian", "superpowers"],
  "userConfig": {
    "jira_url": {
      "type": "string",
      "title": "Jira site URL",
      "description": "Your Jira Cloud site, e.g. https://your-domain.atlassian.net",
      "required": true
    },
    "jira_email": {
      "type": "string",
      "title": "Jira account email",
      "description": "Atlassian account email used for API authentication",
      "required": true
    },
    "jira_api_token": {
      "type": "string",
      "title": "Jira API token",
      "description": "Create one at https://id.atlassian.com/manage-profile/security/api-tokens",
      "sensitive": true,
      "required": true
    }
  }
}
```

- [ ] **Step 3: Validate it**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes (no errors). It's fine if it warns about missing `skills/`/other components — those land in later tasks.

- [ ] **Step 4: Commit**

```bash
cd "C:/ChangJinGithub/jira_claude_plugin"
git add .claude-plugin/plugin.json
git commit -m "Add plugin manifest with Jira userConfig"
```

---

### Task 2: Bundle the mcp-atlassian MCP server

**Files:**
- Create: `.mcp.json`

**Interfaces:**
- Consumes: `userConfig` keys `jira_url`, `jira_email`, `jira_api_token` from Task 1's `plugin.json`.
- Produces: an MCP server named `atlassian` exposing Jira tools (e.g. `jira_search`, `jira_get_issue` — exact names come from whatever version of `mcp-atlassian` the user's `uvx` resolves) that Task 5's `SKILL.md` instructs Claude to call.

- [ ] **Step 1: Create the MCP bundle**

Create `.mcp.json`:

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "${user_config.jira_url}",
        "JIRA_USERNAME": "${user_config.jira_email}",
        "JIRA_API_TOKEN": "${user_config.jira_api_token}"
      }
    }
  }
}
```

- [ ] **Step 2: Validate JSON + plugin**

Run: `node -e "JSON.parse(require('fs').readFileSync('.mcp.json', 'utf8')); console.log('valid json')"`
Expected: prints `valid json` (catches typos before `claude plugin validate` runs, since that command reports the file differently).

Then run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add .mcp.json
git commit -m "Bundle mcp-atlassian as the plugin's Jira MCP server"
```

---

### Task 3: Marketplace listing

**Files:**
- Create: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: `name`, `description`, `version`, `author` from Task 1's `plugin.json` (values must match, since this marketplace entry describes that same plugin).
- Produces: the installable marketplace entry — `source: "./"` means this same repo is both the plugin and its own marketplace, so users run `/plugin marketplace add Chang-Jin-Lee/jira-claude-plugin` then `/plugin install jira-claude-plugin`.

- [ ] **Step 1: Create the marketplace manifest**

Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "jira-claude-plugin",
  "description": "Turn a Jira Kanban board into a doc and backlog, ready to hand off to superpowers.",
  "owner": {
    "name": "Chang-Jin-Lee"
  },
  "plugins": [
    {
      "name": "jira-claude-plugin",
      "description": "Crawl a Jira Kanban board into a document and backlog, then optionally hand off to superpowers to start the work.",
      "version": "0.1.0",
      "source": "./",
      "author": {
        "name": "Chang-Jin-Lee"
      }
    }
  ]
}
```

- [ ] **Step 2: Validate**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin\.claude-plugin\marketplace.json"`
Expected: passes.

Then run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "Add self-hosted marketplace listing"
```

---

### Task 4: LICENSE

**Files:**
- Create: `LICENSE`

**Interfaces:**
- Consumes: `license: "MIT"` and `author.name: "Chang-Jin-Lee"` from Task 1's `plugin.json` (must stay consistent).
- Produces: nothing consumed by later tasks — this is a leaf file.

- [ ] **Step 1: Create the MIT license**

Create `LICENSE`:

```
MIT License

Copyright (c) 2026 Chang-Jin-Lee

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Commit**

```bash
git add LICENSE
git commit -m "Add MIT license"
```

---

### Task 5: The jira-to-backlog skill

**Files:**
- Create: `skills/jira-to-backlog/SKILL.md`

**Interfaces:**
- Consumes: the `atlassian` MCP server's tools from Task 2 (referenced generically by name pattern, not hardcoded, since `mcp-atlassian`'s exact tool names can shift between versions); `$ARGUMENTS` as the optional board name/key typed after the skill invocation.
- Produces: `jira-docs/<BOARD-KEY>.md` and `jira-docs/<BOARD-KEY>-backlog.md` in the user's current project directory (not this repo) — the two deliverables the README (Task 6) documents as "what you get".

- [ ] **Step 1: Confirm the skill doesn't exist yet**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes but the plugin currently has zero skills — there is nothing to invoke yet. (This is the "red" step for this task: no `/jira-claude-plugin:jira-to-backlog` command exists.)

- [ ] **Step 2: Write the skill**

Create `skills/jira-to-backlog/SKILL.md`:

```markdown
---
description: Crawl a Jira Kanban board into one consolidated document and a backlog, then optionally hand off to superpowers. Use when the user names a Jira board/project and asks to document it, summarize it, turn it into a backlog, or start work on it.
---

# Jira board → doc → backlog

## 0. Prerequisites check

Confirm Jira MCP tools are available (tools exposed by the `atlassian` MCP
server this plugin bundles, typically named like `jira_search` /
`jira_get_issue`). If none are visible:

- Tell the user Jira isn't reachable yet.
- Ask them to run `/plugin` and fill in (or re-check) this plugin's
  `jira_url` / `jira_email` / `jira_api_token` configuration, and confirm
  `uv`/`uvx` is installed on their machine (`uvx --version`).
- Stop here until it's fixed.

## 1. Resolve the board

If `$ARGUMENTS` (or the user's message) names a board/project, try to
resolve it directly — exact key or name match first. If nothing was given,
or nothing matches:

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

This mirrors the same recursive, deduplicated crawl that the companion
`Export-JiraTree.ps1` project already does directly against the Jira REST
API — same idea, done here through MCP tool calls instead.

For each issue, record: key, title/summary, full description, issue type,
status, assignee, priority, and its Jira URL (`<jira_url>/browse/<KEY>`).

## 4. Write the consolidated document

Save one Markdown file to `jira-docs/<BOARD-KEY>.md` in the user's current
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

From the tree just captured, write `jira-docs/<BOARD-KEY>-backlog.md`: a
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
  they'd like to install that plugin now
  (`/plugin marketplace add obra/superpowers-marketplace` then
  `/plugin install superpowers`). If yes, walk them through it, then ask
  the question below. If no, stop here.
- If `superpowers` skills are available, ask whether to continue straight
  into brainstorming/writing-plans using `jira-docs/<BOARD-KEY>-backlog.md`
  as the input, or stop here so they can review the files first.

Only invoke a superpowers skill after the user explicitly says yes to that
question.
```

- [ ] **Step 3: Validate**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes — the plugin now has one skill.

- [ ] **Step 4: Load it locally and confirm it's discoverable**

Run: `claude --plugin-dir "C:\ChangJinGithub\jira_claude_plugin" --print "/help"`
Expected: output includes `jira-claude-plugin:jira-to-backlog` in the listed skills/commands. (If `--print` doesn't enumerate skills in this Claude Code version, instead run `claude --plugin-dir "C:\ChangJinGithub\jira_claude_plugin"` interactively for a moment and check `/help` by hand, then exit — either way, confirm the skill name appears before moving on.)

- [ ] **Step 5: Commit**

```bash
git add skills/jira-to-backlog/SKILL.md
git commit -m "Add jira-to-backlog skill: board -> doc -> backlog -> superpowers handoff"
```

---

### Task 6: README (product-facing)

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the plugin name (`jira-claude-plugin`) and skill name (`jira-to-backlog`) from Tasks 1 and 5, to give the exact install/invocation commands; the `jira-docs/<BOARD-KEY>.md` / `jira-docs/<BOARD-KEY>-backlog.md` output paths from Task 5, to describe "what you get".
- Produces: nothing consumed by later tasks — this is the human-facing entry point to the whole repo.

- [ ] **Step 1: Write the README**

Create `README.md`:

```markdown
# Jira → Backlog for Claude Code

Turn a Jira Kanban board into a ready-to-work backlog, right from your terminal.

## What it does

Point this at a Jira board and it will:

1. Read through every issue on the board, and every subtask underneath them
2. Put it all into one easy-to-read document
3. Turn that document into a prioritized backlog, with acceptance criteria for each item
4. Ask whether you want to jump straight into building it, using the [superpowers](https://github.com/obra/superpowers) skill pack

## Why

Reading through a whole board's epics, stories, and subtasks just to write a
spec is repetitive busywork. This plugin does the reading for you, so you
can go from "here's our board" to "here's what to build, and in what order"
in one step.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- A Jira Cloud site, with your account email and an API token
- [uv](https://docs.astral.sh/uv/) installed on your machine (used to run the Jira connector)

### Get a Jira API token

1. Go to your Atlassian account's [API token page](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create a token and copy it — it's only shown once

## Install

```
/plugin marketplace add Chang-Jin-Lee/jira-claude-plugin
/plugin install jira-claude-plugin
```

The first time you use it, Claude Code will ask for your Jira site URL,
your account email, and the API token you created above. These are stored
securely on your machine — never in this repo, never in plain text.

## Usage

Just ask, in your own words:

> "지라 KAN 보드 문서화해서 백로그 만들어줘"
> "Turn our Jira board APP into a backlog"

Or invoke it directly:

```
/jira-claude-plugin:jira-to-backlog KAN
```

If you don't name a board, Claude will list the boards you have access to
and let you pick one.

## What you get

Two files, saved into your current project:

- `jira-docs/<BOARD>.md` — the whole board in one document, one section per
  issue, nested to match epic → story → subtask
- `jira-docs/<BOARD>-backlog.md` — a prioritized backlog built from that
  document, with acceptance criteria per item

Once those are ready, Claude will ask whether you'd like to start working
through the backlog with [superpowers](https://github.com/obra/superpowers)
— offering to install it first if you don't already have it.

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add product-facing README"
```

---

### Task 7: Final validation and push

**Files:**
- Modify: none (validation only)

**Interfaces:**
- Consumes: the complete plugin from Tasks 1-6.
- Produces: a pushed, installable `master` branch at `https://github.com/Chang-Jin-Lee/jira-claude-plugin`.

- [ ] **Step 1: Strict validation**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin" --strict`
Expected: passes with no errors or warnings. Fix anything it flags before continuing.

- [ ] **Step 2: Local install smoke test**

Run: `claude --plugin-dir "C:\ChangJinGithub\jira_claude_plugin" --print "/help"`
Expected: `jira-claude-plugin:jira-to-backlog` is listed. This confirms the plugin loads cleanly end to end, independent of the marketplace/install flow (which needs a real GitHub fetch and can't be exercised from inside this session).

- [ ] **Step 3: Confirm working tree is clean**

Run: `cd "C:/ChangJinGithub/jira_claude_plugin" && git status`
Expected: `nothing to commit, working tree clean` (everything from Tasks 1-6 was already committed).

- [ ] **Step 4: Push**

```bash
git push origin master
```

Expected: pushes cleanly (no force needed — every task already committed and this branch has been pushed incrementally after earlier tasks too, per the Global Constraints).

- [ ] **Step 5: Report the final state to the user**

Confirm to the user: repo URL, install commands, and that
`claude plugin validate --strict` passed.
