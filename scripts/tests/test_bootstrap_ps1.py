"""Checks on scripts/bootstrap.ps1, the Windows half of the uv bootstrap.

The Korean messages here are load-bearing: Windows PowerShell 5.1 decodes a
BOM-less .ps1 with the system ANSI codepage and turns them all into mojibake,
which is invisible until a user on a Korean Windows box sees garbage.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def test_is_saved_with_a_utf8_bom():
    assert SCRIPT.read_bytes()[:3] == b"\xef\xbb\xbf", (
        "bootstrap.ps1 lost its UTF-8 BOM; PowerShell 5.1 will mangle its "
        "Korean output"
    )


def test_body_is_valid_utf8_after_the_bom():
    SCRIPT.read_text(encoding="utf-8-sig")


def test_sets_console_output_encoding():
    # The BOM fixes reading the file; this fixes writing to the console.
    assert "[Console]::OutputEncoding" in SCRIPT.read_text(encoding="utf-8-sig")


@pytest.mark.skipif(POWERSHELL is None, reason="needs PowerShell")
def test_parses_cleanly():
    check = (
        "$e=$null;"
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',"
        "[ref]$null,[ref]$e);"
        "if($e){$e|%{$_.Message};exit 1}else{exit 0}"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="needs PowerShell")
def test_stays_silent_when_uv_is_already_available():
    # Inherits the real PATH, where uv lives; must be a no-op.
    if shutil.which("uv") is None:
        pytest.skip("uv not installed here")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_mirrors_the_posix_script_contract():
    """Both halves must offer the same knobs, or the skill's instructions are
    only true on one platform."""
    ps1 = SCRIPT.read_text(encoding="utf-8-sig")
    sh = (SCRIPT.parent / "bootstrap.sh").read_text(encoding="utf-8")
    for knob in ("JIRA_PLUGIN_NO_BOOTSTRAP", "JIRA_PLUGIN_UV_INSTALLER"):
        assert knob in ps1, f"{knob} missing from bootstrap.ps1"
        assert knob in sh, f"{knob} missing from bootstrap.sh"
    for token in ("mcp-atlassian", "astral.sh"):
        assert token in ps1 and token in sh
