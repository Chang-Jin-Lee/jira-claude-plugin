"""Exercise scripts/bootstrap.sh against a controlled PATH.

This is the one part of the plugin that runs when uv is absent, so the tests
build fake PATHs rather than mocking: what matters is what the script does
when `uv` genuinely cannot be found.
"""
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap.sh"
SH = shutil.which("sh") or shutil.which("bash")


def _shell_utils_dir():
    """Where mkdir/chmod/sh live, in the shell's own path syntax. Asking the
    shell matters on Windows: a PATH entry like "C:/Program Files/Git/usr/bin"
    gets split on the drive-letter colon, and nothing is found."""
    if SH is None:
        return None
    out = subprocess.run(
        [SH, "-c", 'dirname "$(command -v mkdir)"'], capture_output=True, text=True
    )
    return out.stdout.strip() or None


# uv deliberately does not live here, so the script still sees uv as missing.
SHELL_UTILS = _shell_utils_dir()

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX shell")


def make_exe(directory: Path, name: str, body: str = "exit 0") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def run(tmp_path, path_dirs, windows=True, shell_utils=True, **env):
    """Run bootstrap.sh with PATH limited to path_dirs, on a chosen platform.

    Paths go in POSIX form: the script runs under sh, where a Windows
    backslash is an escape character, not a separator.
    """
    dirs = [Path(d).as_posix() for d in path_dirs]
    if shell_utils and SHELL_UTILS:
        dirs.append(SHELL_UTILS)
    base = {
        "PATH": ":".join(dirs),
        "HOME": (tmp_path / "home").as_posix(),
        "USERPROFILE": (tmp_path / "home").as_posix(),
    }
    if windows:
        base["SystemRoot"] = "C:\\Windows"
    base.update(env)
    # The script prints Korean; decode as UTF-8 rather than the Windows
    # console codepage pytest would otherwise pick.
    return subprocess.run(
        [SH, str(SCRIPT)],
        env=base,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_says_nothing_when_uv_is_already_available(tmp_path):
    bin_dir = tmp_path / "bin"
    make_exe(bin_dir, "uv")
    make_exe(bin_dir, "uvx")
    result = run(tmp_path, [bin_dir])
    assert result.returncode == 0
    assert result.stdout == ""


def test_points_at_a_terminal_restart_when_uv_is_installed_but_off_path(tmp_path):
    # uv's installer edits PATH; a terminal that was already open never sees
    # it. Installing a second copy would not help, so don't.
    home = tmp_path / "home"
    make_exe(home / ".local" / "bin", "uv")
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run(tmp_path, [empty])
    assert result.returncode == 0
    assert "PATH에 없습니다" in result.stdout
    assert "완전히 종료" in result.stdout


def test_opt_out_explains_instead_of_installing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run(tmp_path, [empty], JIRA_PLUGIN_NO_BOOTSTRAP="1")
    assert result.returncode == 0
    assert "docs.astral.sh" in result.stdout
    assert "설치합니다" not in result.stdout


def test_reports_failure_when_no_downloader_is_available(tmp_path):
    # Non-Windows shape with nothing on PATH to fetch the installer with.
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run(tmp_path, [empty], windows=False, shell_utils=False)
    assert result.returncode == 0
    assert "curl" in result.stdout


@pytest.mark.parametrize("marker", ["SYSTEMROOT", "WINDIR", "MSYSTEM", "OS"])
def test_detects_windows_without_uname_on_path(tmp_path, marker):
    # A hook's PATH is not ours to assume, so platform detection must not
    # depend on `uname` being reachable — and Windows upper-cases env names,
    # so the spelling that arrives is not always the one you wrote.
    empty = tmp_path / "empty"
    empty.mkdir()
    value = "Windows_NT" if marker == "OS" else "C:\\Windows"
    result = run(tmp_path, [empty], windows=False, shell_utils=False, **{marker: value})
    assert "curl" not in result.stdout, "fell through to the non-Windows branch"


def fake_installer(target: Path, landed: Path) -> str:
    """A JIRA_PLUGIN_UV_INSTALLER that drops uv/uvx where uv's real installer
    puts them, and records whether the prefetch was invoked."""
    where, mark = target.as_posix(), landed.as_posix()
    return (
        f'mkdir -p "{where}"; '
        f"printf '#!/bin/sh\\nexit 0\\n' > \"{where}/uv\"; "
        f'chmod 755 "{where}/uv"; '
        f"printf '#!/bin/sh\\ntouch \\\"{mark}\\\"\\n' > \"{where}/uvx\"; "
        f'chmod 755 "{where}/uvx"'
    )


def test_installs_and_prefetches_then_asks_for_a_restart(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    target = tmp_path / "home" / ".local" / "bin"
    landed = tmp_path / "prefetch-ran"
    result = run(
        tmp_path, [empty], JIRA_PLUGIN_UV_INSTALLER=fake_installer(target, landed)
    )
    assert result.returncode == 0, result.stderr
    assert (target / "uv").exists(), f"installer never ran: {result.stdout}"
    assert "설치 완료" in result.stdout
    # Must ask for a terminal restart, not just a Claude Code restart: uv's
    # installer edits the user PATH, which an already-open terminal never sees,
    # so relaunching from it would loop straight back to the off-PATH branch.
    assert "터미널" in result.stdout
    assert "다시 실행" in result.stdout


def test_prefetches_the_server_package_with_the_uv_it_just_installed(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    target = tmp_path / "home" / ".local" / "bin"
    landed = tmp_path / "prefetch-ran"
    run(tmp_path, [empty], JIRA_PLUGIN_UV_INSTALLER=fake_installer(target, landed))
    # The freshly installed uvx is not on PATH yet, so it must be called by
    # path — otherwise nothing is downloaded and the next session stalls again.
    deadline = time.monotonic() + 15
    while not landed.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert landed.exists(), "server package prefetch never started"


def test_installer_override_wins_over_the_platform_default(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    target = tmp_path / "home" / ".local" / "bin"
    landed = tmp_path / "prefetch-ran"
    # Non-Windows with no curl/wget would normally give up; the override must
    # still be used.
    result = run(
        tmp_path,
        [empty],
        windows=False,
        JIRA_PLUGIN_UV_INSTALLER=fake_installer(target, landed),
    )
    assert "curl" not in result.stdout
    assert "설치 완료" in result.stdout


def test_never_blocks_on_the_download(tmp_path):
    """The prefetch must be detached; a slow child must not hold the hook."""
    bin_dir = tmp_path / "bin"
    home = tmp_path / "home"
    target = home / ".local" / "bin"
    make_exe(target, "uv")
    make_exe(target, "uvx", "sleep 30")
    make_exe(
        bin_dir,
        "powershell",
        "exit 0",
    )
    make_exe(bin_dir, "curl", "exit 0")
    import time

    started = time.monotonic()
    result = run(tmp_path, [bin_dir])
    elapsed = time.monotonic() - started
    assert result.returncode == 0
    assert elapsed < 20, f"bootstrap blocked for {elapsed:.1f}s"
