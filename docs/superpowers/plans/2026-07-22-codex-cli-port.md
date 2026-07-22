# Codex CLI Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this plugin installable and usable from Codex CLI, alongside its existing Claude Code support, without changing any Claude Code behavior.

**Architecture:** Add a sibling `.codex-plugin/plugin.json` manifest and `.agents/plugins/marketplace.json` marketplace entry (mirroring `obra/superpowers`'s multi-harness layout), reusing the existing `skills/` and `scripts/` directories unchanged in place. Since Codex has no `userConfig` equivalent and currently rejects plugin-bundled `hooks`, the Codex manifest declares its `atlassian` MCP server inline with `${VAR}` env substitution instead of Claude's hook + `run_mcp.py` wrapper. The one shared `skills/jira-to-backlog/SKILL.md` gets its Claude-only wording (step 0, step 6) generalized so it reads correctly from either harness.

**Tech Stack:** Python 3 (stdlib `json`/`os`/`pathlib` + `requests`, `textual`), pytest + pytest-asyncio + requests-mock (via `uv run --with ...`), JSON plugin manifests (Claude Code and Codex CLI plugin formats).

## Global Constraints

- Env var names for Codex credentials must be exactly `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` — the same names `mcp-atlassian` itself expects — with no remapping layer anywhere in the Codex path.
- Claude Code's existing hook, `userConfig`, and `scripts/run_mcp.py` wrapper are not touched by this plan; their behavior must remain byte-for-byte identical.
- `.codex-plugin/plugin.json` must NOT declare a `hooks` field (Codex plugin validation currently rejects bundled hooks; confirmed via `openai/codex`'s own `plugin-creator` skill reference doc).
- Exactly one shared `skills/jira-to-backlog/SKILL.md` serves both harnesses — no per-harness duplicate skill file.
- No new runtime dependencies beyond what's already used (`uv`/`uvx`, `mcp-atlassian`, `textual`, `requests`).
- Run the full test suite with: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/ -v` (from repo root; this is the project's documented test command per `CONTRIBUTING.md`).
- Validate the Claude Code manifest still passes with: `claude plugin validate .` (from repo root) — must print `✔ Validation passed`.
- Per `CONTRIBUTING.md`'s version-lockstep convention, keep `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.codex-plugin/plugin.json` on the same `version` value at all times.

---

### Task 1: Environment-variable fallback for credential loading

**Files:**
- Modify: `scripts/sync_credentials.py`
- Modify: `scripts/browse_tree.py`
- Test: `scripts/tests/test_sync_credentials.py`
- Test: `scripts/tests/test_browse_tree_data.py`

**Interfaces:**
- Produces: `sync_credentials.load_credentials(path: Path) -> dict | None` — reads `~/.jira-claude-plugin/credentials.json` if it exists and has all three keys (`jira_url`, `jira_email`, `jira_api_token`) non-empty; otherwise falls back to `os.environ["JIRA_URL"]` / `["JIRA_USERNAME"]` / `["JIRA_API_TOKEN"]`; returns `None` if neither source is complete. `browse_tree.py` imports and uses this directly (no separate copy).

- [ ] **Step 1: Write the failing tests for the new fallback function**

Add to `scripts/tests/test_sync_credentials.py` (append after the existing tests):

```python
def test_load_credentials_reads_file_when_present(tmp_path):
    creds = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    assert sc.load_credentials(path) == creds


def test_load_credentials_falls_back_to_env_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USERNAME", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    result = sc.load_credentials(tmp_path / "nope.json")
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "t",
    }


def test_load_credentials_returns_none_when_file_missing_and_env_incomplete(monkeypatch, tmp_path):
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert sc.load_credentials(tmp_path / "nope.json") is None


def test_load_credentials_falls_back_to_env_when_file_incomplete(monkeypatch, tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps({"jira_url": "", "jira_email": "", "jira_api_token": ""}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USERNAME", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    result = sc.load_credentials(path)
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "t",
    }
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_sync_credentials.py -v`
Expected: 4 new FAILs with `AttributeError: module 'sync_credentials' has no attribute 'load_credentials'`

- [ ] **Step 3: Implement `load_credentials` in `sync_credentials.py`**

Add this function to `scripts/sync_credentials.py` (after `write_credentials`, before `browse_command_hint`):

```python
def load_credentials(path: Path) -> dict | None:
    if path.exists():
        creds = json.loads(path.read_text(encoding="utf-8"))
        if all(creds.get(key) for key in ("jira_url", "jira_email", "jira_api_token")):
            return creds
    env_creds = {
        "jira_url": os.environ.get("JIRA_URL", ""),
        "jira_email": os.environ.get("JIRA_USERNAME", ""),
        "jira_api_token": os.environ.get("JIRA_API_TOKEN", ""),
    }
    if not all(env_creds.values()):
        return None
    return env_creds
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_sync_credentials.py -v`
Expected: PASS (all tests in the file, including the 4 new ones)

- [ ] **Step 5: Update `browse_tree.py` to use the shared function**

In `scripts/browse_tree.py`, replace this import line:

```python
from sync_credentials import credentials_path  # noqa: E402
```

with:

```python
from sync_credentials import credentials_path, load_credentials  # noqa: E402
```

Then delete `browse_tree.py`'s own local definition (these exact 4 lines, right after the import block):

```python
def load_credentials(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

Then update the "no credentials" message in `main()` — replace:

```python
    creds = load_credentials(credentials_path())
    if creds is None:
        print(
            "자격증명 파일이 없습니다 - 이 플러그인이 활성화된 Claude Code "
            "세션을 한 번 시작한 뒤 다시 실행하세요."
        )
        return 1
```

with:

```python
    creds = load_credentials(credentials_path())
    if creds is None:
        print(
            "자격증명을 찾을 수 없습니다 - Claude Code에서는 이 플러그인이 "
            "활성화된 세션을 한 번 시작하고, 다른 도구에서는 JIRA_URL / "
            "JIRA_USERNAME / JIRA_API_TOKEN 환경변수를 설정한 뒤 다시 "
            "실행하세요."
        )
        return 1
```

- [ ] **Step 6: Update the existing browse-tree test for determinism**

In `scripts/tests/test_browse_tree_data.py`, replace:

```python
def test_load_credentials_returns_none_when_missing(tmp_path):
    assert bt.load_credentials(tmp_path / "nope.json") is None
```

with:

```python
def test_load_credentials_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert bt.load_credentials(tmp_path / "nope.json") is None
```

(This test previously relied on the file-missing case always returning `None`; now that `load_credentials` falls back to env vars, the test must explicitly clear those three vars so it doesn't flake depending on the running shell's environment.)

- [ ] **Step 7: Run the full suite to verify nothing broke**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/ -v`
Expected: PASS (all tests, including the untouched `test_browse_tree_app.py` and `test_run_mcp.py`)

- [ ] **Step 8: Commit**

```bash
git add scripts/sync_credentials.py scripts/browse_tree.py scripts/tests/test_sync_credentials.py scripts/tests/test_browse_tree_data.py
git commit -m "$(cat <<'EOF'
Add env-var fallback for credential loading

Lets the standalone tree browser (and, transitively, any future
non-Claude caller) work from JIRA_URL/JIRA_USERNAME/JIRA_API_TOKEN
env vars when the hook-synced credentials file doesn't exist —
needed for Codex CLI, which has no session-hook equivalent.
EOF
)"
```

---

### Task 2: Codex plugin manifest (`.codex-plugin/plugin.json`)

**Files:**
- Create: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json` (version bump only)
- Modify: `.claude-plugin/marketplace.json` (version bump only)
- Test: `scripts/tests/test_codex_plugin_manifest.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `.codex-plugin/plugin.json` — the file later tasks (3, 5, 6) reference by path.

- [ ] **Step 1: Write the failing manifest-shape test**

Create `scripts/tests/test_codex_plugin_manifest.py`:

```python
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"


def _load():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_has_required_top_level_fields():
    manifest = _load()
    assert manifest["name"] == "jira-claude-plugin"
    assert manifest["version"] == "0.1.8"
    assert manifest["description"]
    assert manifest["author"]["name"]
    assert manifest["skills"] == "./skills/"


def test_manifest_has_no_hooks_field():
    manifest = _load()
    assert "hooks" not in manifest


def test_manifest_declares_atlassian_mcp_server_with_env_substitution():
    manifest = _load()
    server = manifest["mcpServers"]["atlassian"]
    assert server["command"] == "uvx"
    assert server["args"] == ["mcp-atlassian"]
    assert server["env"] == {
        "JIRA_URL": "${JIRA_URL}",
        "JIRA_USERNAME": "${JIRA_USERNAME}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}",
        "READ_ONLY_MODE": "true",
    }


def test_manifest_has_required_interface_fields():
    manifest = _load()
    interface = manifest["interface"]
    for field in (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "defaultPrompt",
    ):
        assert field in interface
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_codex_plugin_manifest.py -v`
Expected: FAIL with `FileNotFoundError` (the manifest doesn't exist yet)

- [ ] **Step 3: Create `.codex-plugin/plugin.json`**

```json
{
  "name": "jira-claude-plugin",
  "version": "0.1.8",
  "description": "Crawl a Jira Kanban board into a document and backlog, then optionally hand off to superpowers to start the work.",
  "author": {
    "name": "Chang-Jin-Lee"
  },
  "homepage": "https://github.com/Chang-Jin-Lee/jira-claude-plugin",
  "repository": "https://github.com/Chang-Jin-Lee/jira-claude-plugin",
  "license": "MIT",
  "keywords": ["jira", "kanban", "backlog", "atlassian", "superpowers"],
  "skills": "./skills/",
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
  },
  "interface": {
    "displayName": "Jira → Backlog",
    "shortDescription": "Crawl a Jira board into a doc and backlog, then hand off to superpowers.",
    "longDescription": "Crawl a Jira Kanban board into a document and backlog, then optionally hand off to superpowers to start the work.",
    "developerName": "Chang-Jin-Lee",
    "category": "Productivity",
    "capabilities": ["Interactive", "Read", "Write"],
    "defaultPrompt": [
      "Turn our Jira board APP into a backlog.",
      "Document this Jira board and summarize it."
    ]
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_codex_plugin_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Bump the shared version to 0.1.8**

In `.claude-plugin/plugin.json`, change:

```json
  "version": "0.1.7",
```

to:

```json
  "version": "0.1.8",
```

In `.claude-plugin/marketplace.json`, change:

```json
      "version": "0.1.7",
```

to:

```json
      "version": "0.1.8",
```

- [ ] **Step 6: Validate the Claude Code manifest still passes**

Run: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 7: Commit**

```bash
git add .codex-plugin/plugin.json .claude-plugin/plugin.json .claude-plugin/marketplace.json scripts/tests/test_codex_plugin_manifest.py
git commit -m "$(cat <<'EOF'
Add Codex CLI plugin manifest

Mirrors obra/superpowers' multi-harness layout: a sibling
.codex-plugin/plugin.json alongside .claude-plugin/, reusing the
existing skills/ directory. The atlassian MCP server is declared
inline with ${VAR} env substitution instead of Claude's hook +
run_mcp.py wrapper, since Codex has no userConfig equivalent and
currently rejects plugin-bundled hooks.
EOF
)"
```

---

### Task 3: Codex marketplace entry (`.agents/plugins/marketplace.json`)

**Files:**
- Create: `.agents/plugins/marketplace.json`
- Test: `scripts/tests/test_codex_marketplace_manifest.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 (independent file).
- Produces: `.agents/plugins/marketplace.json` — referenced by Task 5's README install instructions and Task 6's live verification.

- [ ] **Step 1: Write the failing marketplace-shape test**

Create `scripts/tests/test_codex_marketplace_manifest.py`:

```python
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"


def test_marketplace_lists_the_plugin_with_local_root_source():
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    assert marketplace["name"] == "jira-claude-plugin"
    entries = marketplace["plugins"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "jira-claude-plugin"
    assert entry["source"] == {"source": "url", "url": "./"}
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert entry["category"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_codex_marketplace_manifest.py -v`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Create `.agents/plugins/marketplace.json`**

```json
{
  "name": "jira-claude-plugin",
  "interface": {
    "displayName": "Jira Claude Plugin"
  },
  "plugins": [
    {
      "name": "jira-claude-plugin",
      "source": {
        "source": "url",
        "url": "./"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/test_codex_marketplace_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/plugins/marketplace.json scripts/tests/test_codex_marketplace_manifest.py
git commit -m "$(cat <<'EOF'
Add Codex CLI marketplace entry

.agents/plugins/marketplace.json registers this repo root as the
plugin source (source: url, url: ./), matching how
obra/superpowers registers itself for Codex.
EOF
)"
```

---

### Task 4: Generalize `SKILL.md` wording away from Claude-only commands

**Files:**
- Modify: `skills/jira-to-backlog/SKILL.md`

**Interfaces:**
- Consumes: nothing (prose-only change).
- Produces: nothing code-facing; later tasks don't depend on this file's exact wording.

- [ ] **Step 1: Generalize step 0 (prerequisites check)**

In `skills/jira-to-backlog/SKILL.md`, replace:

```markdown
- Tell the user Jira isn't reachable yet.
- Ask them to run `/plugin` and fill in (or re-check) this plugin's
  `jira_url` / `jira_email` / `jira_api_token` configuration, and confirm
  `uv`/`uvx` is installed on their machine (`uvx --version`).
- Stop here until it's fixed.
```

with:

```markdown
- Tell the user Jira isn't reachable yet.
- Ask them to (re-)configure this plugin's Jira access for whichever tool
  they're running it from — see this plugin's README for the exact steps
  (Claude Code: `/plugin` and its `jira_url` / `jira_email` /
  `jira_api_token` fields; other tools: the `JIRA_URL` / `JIRA_USERNAME` /
  `JIRA_API_TOKEN` environment variables) — and confirm `uv`/`uvx` is
  installed on their machine (`uvx --version`).
- Stop here until it's fixed.
```

- [ ] **Step 2: Generalize step 6 (superpowers handoff)**

In the same file, replace:

```markdown
- If no `superpowers` skills are available in this session, ask whether
  they'd like to install that plugin now
  (`/plugin marketplace add obra/superpowers-marketplace` then
  `/plugin install superpowers`). If yes, walk them through it, then ask
  the question below. If no, stop here.
```

with:

```markdown
- If no `superpowers` skills are available in this session, ask whether
  they'd like to install that plugin now, using whichever command matches
  the tool this skill is running in (Claude Code: `/plugin marketplace add
  obra/superpowers-marketplace` then `/plugin install superpowers`; Codex
  CLI: `codex plugin marketplace add obra/superpowers-marketplace` then
  `codex plugin add superpowers@...`, using the marketplace name printed
  by that add command). If yes, walk them through it, then ask the
  question below. If no, stop here.
```

- [ ] **Step 3: Manually verify the edits read correctly**

Read the full modified file back and confirm: step 0 no longer assumes
`/plugin` is the only configuration path, step 6 no longer hardcodes only
Claude Code's install commands, and steps 1-5 (crawl logic) are
byte-for-byte unchanged. This is a prose skill file, not code — there is
no automated test for wording; this manual re-read is the verification
step, matching how this repo's prior `SKILL.md` wording change
(2026-07-17 tree-browser design) was verified.

- [ ] **Step 4: Commit**

```bash
git add skills/jira-to-backlog/SKILL.md
git commit -m "$(cat <<'EOF'
Generalize SKILL.md wording for non-Claude harnesses

Step 0's credential-check guidance and step 6's superpowers-install
handoff no longer hardcode Claude Code's /plugin commands, so the
same shared skill file reads correctly when run from Codex CLI too.
EOF
)"
```

---

### Task 5: Document Codex CLI install in README and CONTRIBUTING

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: the marketplace name (`jira-claude-plugin`) from Task 3 and the env var names from Task 1/2.
- Produces: nothing code-facing.

- [ ] **Step 1: Update the README title and requirements**

In `README.md`, replace:

```markdown
# Jira → Backlog for Claude Code
```

with:

```markdown
# Jira → Backlog for Claude Code & Codex CLI
```

Replace:

```markdown
## Requirements

- [Claude Code](https://claude.com/claude-code)
- A Jira Cloud site, with your account email and an API token
- [uv](https://docs.astral.sh/uv/) installed on your machine (used to run the Jira connector and the tree browser)
```

with:

```markdown
## Requirements

- [Claude Code](https://claude.com/claude-code) or [Codex CLI](https://developers.openai.com/codex)
- A Jira Cloud site, with your account email and an API token
- [uv](https://docs.astral.sh/uv/) installed on your machine (used to run the Jira connector and the tree browser)
```

- [ ] **Step 2: Split the Install section by harness**

Replace:

```markdown
## Install

```
/plugin marketplace add Chang-Jin-Lee/jira-claude-plugin
/plugin install jira-claude-plugin
```

Type each line exactly as shown, in one go. If you instead run `/plugin`
with no arguments and use the interactive menu, its "Enter marketplace
source" field wants just `Chang-Jin-Lee/jira-claude-plugin` — don't type
`marketplace add` again in there, or Claude Code will treat the whole
string as the repo path and reject it.

The first time you use it, Claude Code will ask for your Jira site URL,
your account email, and the API token you created above. These are stored
securely on your machine — never in this repo, never in plain text.
```

with:

```markdown
## Install

### Claude Code

```
/plugin marketplace add Chang-Jin-Lee/jira-claude-plugin
/plugin install jira-claude-plugin
```

Type each line exactly as shown, in one go. If you instead run `/plugin`
with no arguments and use the interactive menu, its "Enter marketplace
source" field wants just `Chang-Jin-Lee/jira-claude-plugin` — don't type
`marketplace add` again in there, or Claude Code will treat the whole
string as the repo path and reject it.

The first time you use it, Claude Code will ask for your Jira site URL,
your account email, and the API token you created above. These are stored
securely on your machine — never in this repo, never in plain text.

### Codex CLI

```
codex plugin marketplace add Chang-Jin-Lee/jira-claude-plugin
codex plugin add jira-claude-plugin@jira-claude-plugin
```

Codex plugins don't have an interactive secret-entry screen yet, so set
these three environment variables yourself before first use (e.g. in
`~/.zshrc` or `~/.bashrc`), then start a new Codex session:

```
export JIRA_URL="https://your-domain.atlassian.net"
export JIRA_USERNAME="you@example.com"
export JIRA_API_TOKEN="<the token you created above>"
```
```

- [ ] **Step 3: Update the CONTRIBUTING.md project layout list**

In `CONTRIBUTING.md`, replace:

```markdown
- `hooks/hooks.json`, `.mcp.json`, `.claude-plugin/plugin.json` — plugin wiring
```

with:

```markdown
- `hooks/hooks.json`, `.mcp.json`, `.claude-plugin/plugin.json` — Claude Code plugin wiring
- `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json` — Codex CLI plugin wiring (no hook; the `atlassian` MCP server reads `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN` from the environment directly)
```

- [ ] **Step 4: Add a note to the version-bump rule**

In `CONTRIBUTING.md`, replace:

```markdown
- **Bump the version on every hook-affecting change.** If a PR touches
  `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.mcp.json`, or any
  file a hook depends on, bump `"version"` in both `.claude-plugin/plugin.json`
  and `.claude-plugin/marketplace.json` (they must match). Otherwise
  `/plugin update` silently no-ops — installed users never see the fix.
```

with:

```markdown
- **Bump the version on every hook-affecting change.** If a PR touches
  `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.mcp.json`, or any
  file a hook depends on, bump `"version"` in both `.claude-plugin/plugin.json`
  and `.claude-plugin/marketplace.json` (they must match). Otherwise
  `/plugin update` silently no-ops — installed users never see the fix.
  Keep `.codex-plugin/plugin.json`'s `"version"` in lockstep with those
  two as well, even though Codex has no equivalent update-skip failure
  mode — it's simpler to keep one version number across every manifest.
```

- [ ] **Step 5: Manually verify the rendered README**

Read `README.md` back in full and confirm the table of contents still
matches the section structure (no broken anchors), both `## Install`
subsections read correctly, and no Claude-only assumption remains
elsewhere in the file (e.g. the "Browse boards..." section's per-session
hint is still accurate — it's still Claude-only, which is correct, since
Codex has no session-start hook).

- [ ] **Step 6: Commit**

```bash
git add README.md CONTRIBUTING.md
git commit -m "$(cat <<'EOF'
Document Codex CLI install path

Adds a Codex CLI subsection to the Install section (marketplace add
+ plugin add + manual env-var export, since Codex has no
interactive secret-entry screen) and updates CONTRIBUTING.md's
project layout and version-bump notes to cover the new
.codex-plugin/ and .agents/plugins/ files.
EOF
)"
```

---

### Task 6: Live verification against a real Codex CLI (manual, deferred)

**Files:** none (no code changes — this is a verification-only task).

**Interfaces:**
- Consumes: `.codex-plugin/plugin.json` (Task 2), `.agents/plugins/marketplace.json` (Task 3), the env-var fallback (Task 1), and the README instructions (Task 5).

This plan's sandbox has no `codex` CLI installed, so this task cannot be
completed by an agent in this environment — it must be run by the user
on a machine with Codex CLI installed, and is the final gate before
calling the Codex port done.

- [ ] **Step 1: Install the plugin from a local checkout**

```bash
codex plugin marketplace add /absolute/path/to/jira-claude-plugin
codex plugin add jira-claude-plugin@jira-claude-plugin
```

Expected: both commands succeed; `codex plugin list` shows
`jira-claude-plugin` installed.

- [ ] **Step 2: Confirm no duplicate/broken MCP server is loaded**

Start a Codex session and check which MCP servers are connected (however
Codex CLI surfaces this — e.g. its `/mcp` or `/status`-style command, or
verbose startup logs). Confirm exactly one `atlassian` server is present
and it is the inline one from `.codex-plugin/plugin.json` (`uvx
mcp-atlassian`), not a second, broken entry trying to run
`${CLAUDE_PLUGIN_ROOT}/scripts/run_mcp.py` from the repo's root
`.mcp.json`. **This resolves the open risk flagged in the design doc**
(`docs/superpowers/specs/2026-07-22-codex-cli-port-design.md`): whether
Codex's default component discovery also picks up the root `.mcp.json`
despite the inline `mcpServers` declaration. If it does get picked up and
breaks the session, the fix is to relocate/rename the Claude-only
`.mcp.json` so Codex's default discovery no longer finds a file at that
conventional path, without breaking Claude Code's discovery of it (verify
`claude plugin validate .` and a real Claude Code session still work
after any such change).

- [ ] **Step 3: Confirm the skill and MCP tools work end-to-end**

With `JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN` exported per the
README, ask Codex to run the `jira-to-backlog` skill against a real board
or issue key (e.g. the same kind of manual check this repo's
`docs/superpowers/specs/2026-07-17-standalone-tree-browser-design.md`
used for the Claude Code path: a single real issue key). Confirm
`jira-docs/<KEY>.md` and `jira-docs/<KEY>-backlog.md` are written with
real data.

- [ ] **Step 4: Confirm the standalone tree browser works without a Claude Code session**

On a machine (or shell) where `~/.jira-claude-plugin/credentials.json`
does not exist, with the three env vars exported, run:

```bash
uv run --with textual,requests scripts/browse_tree.py
```

Expected: the tree loads real boards (env-var fallback from Task 1 is
exercised), not the "credentials not found" message.

- [ ] **Step 5: Record the result**

Append a dated "Implementation verification" section to
`docs/superpowers/specs/2026-07-22-codex-cli-port-design.md` (matching
the style of the existing verification sections in this repo's other
specs) describing what was actually observed in Steps 1-4, including how
the root-`.mcp.json` discovery risk was resolved. Commit that update on
its own.
