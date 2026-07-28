import subprocess
from types import SimpleNamespace

import server_package as sp


def test_start_command_stays_offline_when_cached():
    # An index resolve inside the 30s connect budget is what killed the server
    # on a cold machine; a cached start never touches the network.
    assert sp.start_command(True) == ["uvx", "--offline", sp.PACKAGE]


def test_start_command_falls_back_to_online_when_nothing_is_cached():
    assert sp.start_command(False) == ["uvx", sp.PACKAGE]


def test_is_cached_probes_offline_and_reads_the_exit_code(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sp.subprocess, "run", fake_run)
    assert sp.is_cached() is True
    assert calls == [["uvx", "--offline", sp.PACKAGE, "--version"]]


def test_is_cached_is_false_when_the_probe_fails(monkeypatch):
    monkeypatch.setattr(sp.subprocess, "run", lambda cmd, **k: SimpleNamespace(returncode=1))
    assert sp.is_cached() is False


def test_is_cached_is_false_when_uvx_is_missing(monkeypatch):
    def boom(cmd, **kwargs):
        raise OSError("uvx not found")

    monkeypatch.setattr(sp.subprocess, "run", boom)
    assert sp.is_cached() is False


def test_is_cached_is_false_when_the_probe_hangs(monkeypatch):
    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 60)

    monkeypatch.setattr(sp.subprocess, "run", timeout)
    assert sp.is_cached() is False


def test_fetch_in_background_detaches_from_the_hook(monkeypatch):
    # A child still holding the hook's stdout would keep Claude Code waiting
    # for the whole download, which is exactly what must not happen.
    seen = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(sp.subprocess, "Popen", fake_popen)
    assert sp.fetch_in_background() is True
    assert seen["cmd"] == ["uvx", sp.PACKAGE, "--version"]
    assert seen["kwargs"]["stdout"] is subprocess.DEVNULL
    assert seen["kwargs"]["stderr"] is subprocess.DEVNULL
    assert seen["kwargs"]["stdin"] is subprocess.DEVNULL
    assert "creationflags" in seen["kwargs"] or seen["kwargs"].get("start_new_session")


def test_fetch_in_background_reports_failure_instead_of_raising(monkeypatch):
    def boom(cmd, **kwargs):
        raise OSError("uvx not found")

    monkeypatch.setattr(sp.subprocess, "Popen", boom)
    assert sp.fetch_in_background() is False


def test_refresh_is_due_when_never_recorded(tmp_path):
    assert sp.is_refresh_due(tmp_path / "server-refreshed", 1_000_000.0) is True


def test_refresh_is_not_due_right_after_recording(tmp_path):
    marker = tmp_path / "server-refreshed"
    sp.record_refresh(marker, 1_000_000.0)
    assert sp.is_refresh_due(marker, 1_000_000.0) is False


def test_refresh_is_due_again_after_the_interval(tmp_path):
    marker = tmp_path / "server-refreshed"
    sp.record_refresh(marker, 1_000_000.0)
    assert sp.is_refresh_due(marker, 1_000_000.0 + sp.REFRESH_INTERVAL_SECONDS + 1) is True


def test_prepare_fetches_and_warns_when_nothing_is_cached(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(sp, "is_cached", lambda: False)
    monkeypatch.setattr(sp, "fetch_in_background", lambda: fetched.append(True) or True)
    notice = sp.prepare(tmp_path, 1_000_000.0)
    assert fetched == [True]
    assert notice and "/mcp" in notice
    # No marker: a first fetch is not a refresh, and must not push the weekly
    # refresh a week out before the package has ever landed.
    assert not sp.refresh_marker(tmp_path).exists()


def _must_not_fetch():
    raise AssertionError("must not fetch when the cache is fresh")


def test_prepare_is_silent_and_does_nothing_when_cache_is_fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "is_cached", lambda: True)
    monkeypatch.setattr(sp, "fetch_in_background", _must_not_fetch)
    sp.record_refresh(sp.refresh_marker(tmp_path), 1_000_000.0)
    assert sp.prepare(tmp_path, 1_000_000.0) is None


def test_prepare_refreshes_quietly_once_the_interval_passes(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(sp, "is_cached", lambda: True)
    monkeypatch.setattr(sp, "fetch_in_background", lambda: fetched.append(True) or True)
    marker = sp.refresh_marker(tmp_path)
    sp.record_refresh(marker, 1_000_000.0)
    later = 1_000_000.0 + sp.REFRESH_INTERVAL_SECONDS + 1
    assert sp.prepare(tmp_path, later) is None
    assert fetched == [True]
    assert sp.is_refresh_due(marker, later) is False


def test_prepare_retries_next_session_when_the_refresh_could_not_start(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "is_cached", lambda: True)
    monkeypatch.setattr(sp, "fetch_in_background", lambda: False)
    marker = sp.refresh_marker(tmp_path)
    assert sp.prepare(tmp_path, 1_000_000.0) is None
    assert sp.is_refresh_due(marker, 1_000_000.0) is True
