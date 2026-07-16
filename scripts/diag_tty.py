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
