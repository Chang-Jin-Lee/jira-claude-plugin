# TTY Passthrough Feasibility Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, with real evidence from this machine, whether a Claude Code `UserPromptExpansion` hook process gets a real attached terminal (so a full-screen arrow-key TUI could render there) or only a piped stdout/stdin (so it can't) — the go/no-go gate the interactive board browser design depends on.

**Architecture:** One diagnostic script, invoked by one `UserPromptExpansion` hook matched to this plugin's skill, reports back (via `hookSpecificOutput.additionalContext`, which lands directly in the conversation) whether `stdin`/`stdout`/`stderr` are real TTYs, and whether the OS console device (`CON` on Windows, `/dev/tty` on POSIX) can be opened directly as a fallback. No UI code, no Jira access — this plan only answers the feasibility question.

**Tech Stack:** Python (via `uv run`, no extra packages needed — stdlib only), Claude Code plugin hooks (`hooks/hooks.json`).

## Global Constraints

- This plan produces throwaway/diagnostic artifacts only. It does not touch
  `skills/jira-to-backlog/SKILL.md`, `.mcp.json`, or any existing file from
  the already-shipped plugin (repo: `C:\ChangJinGithub\jira_claude_plugin`,
  currently at commit `5805303` on `master`).
- Platform for this spike: Windows (the machine this plugin is being
  developed and tested on). The diagnostic must check the Windows console
  device (`CON`), not assume POSIX `/dev/tty`.
- Work directly on `master` (already-approved convention for this repo —
  see prior conversation; no feature branch/worktree).
- Verification tool available: `claude plugin validate <path>` (confirmed
  working on this machine, `claude --version` reports `2.1.206`).
- The manual trigger step in Task 1 requires a human to literally type
  `/jira-claude-plugin:jira-to-backlog` in a live Claude Code chat — the
  `UserPromptExpansion` hook fires on user-typed slash/skill invocation
  parsing, not on the Skill tool being invoked programmatically. No
  subagent can substitute for this step; it must be run by the controller
  or the user in a real session.

---

### Task 1: TTY/console diagnostic script + hook wiring

**Files:**
- Create: `scripts/diag_tty.py`
- Create: `hooks/hooks.json`

**Interfaces:**
- Consumes: nothing (first files in this plan).
- Produces: a `hookSpecificOutput.additionalContext` string, visible
  directly in the conversation the moment the hook fires, reporting
  `stdin_isatty`, `stdout_isatty`, `stderr_isatty` (booleans), and
  `console_device_ok` (boolean) + `console_device_error` (string or null)
  for whether `CON` could be opened directly for read+write. This is the
  full output of this plan — later design work (not part of this plan)
  reads these values to decide the browser's real launch mechanism.

- [ ] **Step 1: Write the diagnostic script**

Create `scripts/diag_tty.py`:

```python
#!/usr/bin/env python3
"""Diagnostic: report whether this process has a real attached terminal.

Run by a UserPromptExpansion hook to answer one question: can a
full-screen, arrow-key-driven TUI render in the same terminal the user is
typing into, when launched this way? Reports results via
hookSpecificOutput.additionalContext so they land directly in the
conversation - no file to go read separately.
"""
import json
import sys


def _console_device_status() -> tuple[bool, str | None]:
    try:
        with open("CON", "r+", encoding="utf-8", errors="replace") as _con:
            _con.fileno()
        return True, None
    except OSError as exc:
        return False, str(exc)


def main() -> int:
    console_ok, console_error = _console_device_status()
    result = {
        "stdin_isatty": sys.stdin.isatty(),
        "stdout_isatty": sys.stdout.isatty(),
        "stderr_isatty": sys.stderr.isatty(),
        "console_device_ok": console_ok,
        "console_device_error": console_error,
    }
    context = (
        "[jira-claude-plugin TTY diagnostic] "
        f"stdin.isatty={result['stdin_isatty']} "
        f"stdout.isatty={result['stdout_isatty']} "
        f"stderr.isatty={result['stderr_isatty']} "
        f"CON_open_ok={result['console_device_ok']} "
        f"CON_open_error={result['console_device_error']}"
    )
    print(json.dumps({"hookSpecificOutput": {"additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the script runs standalone first**

Run: `uv run "C:\ChangJinGithub\jira_claude_plugin\scripts\diag_tty.py"`
Expected: prints one line of JSON to stdout, e.g.
`{"hookSpecificOutput": {"additionalContext": "[jira-claude-plugin TTY diagnostic] stdin.isatty=True stdout.isatty=True stderr.isatty=True CON_open_ok=True CON_open_error=None"}}`
(values will differ depending on how this exact command was run — that's
fine, this step only confirms the script executes without a Python error).

- [ ] **Step 3: Register the hook**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "UserPromptExpansion": [
      {
        "matcher": "jira-claude-plugin:jira-to-backlog",
        "hooks": [
          {
            "type": "command",
            "command": "uv",
            "args": ["run", "${CLAUDE_PLUGIN_ROOT}/scripts/diag_tty.py"]
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Validate the plugin**

Run: `claude plugin validate "C:\ChangJinGithub\jira_claude_plugin"`
Expected: passes (no errors; it's fine if it doesn't specifically validate
hook matcher semantics — that's confirmed by the live trigger in Step 6,
not by static validation).

- [ ] **Step 5: Commit**

```bash
cd "C:/ChangJinGithub/jira_claude_plugin"
git add scripts/diag_tty.py hooks/hooks.json
git commit -m "Add TTY passthrough diagnostic spike (hook + script)"
```

- [ ] **Step 6: Reload and manually trigger (requires a human, not a subagent)**

In a real Claude Code session (this repo's directory), run:
```
/reload-plugins
```
then type, as a literal typed message (not a tool call):
```
/jira-claude-plugin:jira-to-backlog
```

**Expected outcomes and what each means:**

- **The diagnostic line appears in the conversation** (as additional
  context right as the skill's prompt is processed), reporting
  `stdout.isatty=True`: the hook process has a real attached terminal.
  Full arrow-key TUI rendering is very likely feasible via normal
  inherited stdio — proceed with the original interactive-browser design
  using straightforward subprocess inheritance.
- **The diagnostic line appears but reports `stdout.isatty=False` /
  `stdin.isatty=False`, while `CON_open_ok=True`**: the hook's inherited
  stdio is piped (as suspected, since Claude Code needs to parse hook
  stdout as JSON), but the OS console device can still be opened directly.
  Proceed with the interactive-browser design, but the TUI process must
  explicitly open and render to `CON` directly rather than relying on
  inherited `sys.stdout`/`sys.stdin` — this becomes a hard requirement for
  the next plan, not an optional nicety.
- **The diagnostic line never appears at all**: the matcher
  `"jira-claude-plugin:jira-to-backlog"` didn't match this invocation. Try
  again with matcher values `"jira-to-backlog"` and
  `"/jira-claude-plugin:jira-to-backlog"` (edit `hooks/hooks.json`,
  `/reload-plugins`, retry) before concluding the mechanism doesn't work at
  all. Record which matcher form (if any) actually fired.
- **The diagnostic line appears with `CON_open_ok=False`**: record the
  `CON_open_error` value. This is the failure case — escalate to the human
  with this evidence rather than attempting further fixes; per the
  original design's feasibility gate, this means the `UserPromptExpansion`
  + subprocess approach cannot deliver a real arrow-key TUI on this
  platform, and the interactive browser needs a different distribution
  shape (e.g., a standalone command the user runs directly themselves,
  outside the hook system).

- [ ] **Step 7: Record the result**

Whatever the outcome, append one line to
`docs/superpowers/specs/2026-07-16-interactive-board-browser-design.md`
under its "Feasibility spike" section, stating exactly what was observed
(the diagnostic values, which matcher form worked if any, and which of the
four outcomes above applies). Commit this update:

```bash
git add docs/superpowers/specs/2026-07-16-interactive-board-browser-design.md
git commit -m "Record TTY passthrough spike result"
git push origin master
```
