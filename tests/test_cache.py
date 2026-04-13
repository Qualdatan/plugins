# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer qualdatan_plugins.cache."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from qualdatan_plugins.bundle import BundleError
from qualdatan_plugins.cache import BundleCache


def test_default_root_honours_env(tmp_path: Path) -> None:
    cache = BundleCache()
    assert cache.root == tmp_path / "cache"
    assert cache.root.is_dir()


def test_install_from_dir_roundtrip(make_bundle) -> None:
    src = make_bundle("qualdatan/test", "0.1.0")
    # zusaetzliche payload-datei
    (src / "payload.txt").write_text("hello", encoding="utf-8")

    cache = BundleCache()
    ib = cache.install_from_dir(src)

    assert ib.id == "qualdatan/test"
    assert ib.version == "0.1.0"
    assert ib.source == "local"
    assert ib.origin == str(src.resolve())
    assert ib.install_path == cache.path_for("qualdatan/test", "0.1.0")
    assert (ib.install_path / "bundle.yaml").is_file()
    assert (ib.install_path / "payload.txt").read_text(encoding="utf-8") == "hello"
    assert cache.exists("qualdatan/test", "0.1.0")


def test_install_from_dir_expected_id_mismatch(make_bundle) -> None:
    src = make_bundle("qualdatan/test", "0.1.0")
    cache = BundleCache()
    with pytest.raises(BundleError):
        cache.install_from_dir(src, expected_id="qualdatan/other")


def test_install_from_dir_overwrites(make_bundle, tmp_path: Path) -> None:
    src1 = make_bundle("qualdatan/test", "0.1.0", subdir="src1")
    (src1 / "marker.txt").write_text("v1", encoding="utf-8")
    src2 = make_bundle("qualdatan/test", "0.1.0", subdir="src2")
    (src2 / "marker.txt").write_text("v2", encoding="utf-8")

    cache = BundleCache()
    cache.install_from_dir(src1)
    ib2 = cache.install_from_dir(src2)
    assert (ib2.install_path / "marker.txt").read_text(encoding="utf-8") == "v2"


def test_atomic_swap_cleans_up_on_failure(make_bundle, monkeypatch) -> None:
    src = make_bundle("qualdatan/test", "0.1.0")
    cache = BundleCache()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("qualdatan_plugins.cache.os.replace", boom)
    with pytest.raises(OSError):
        cache.install_from_dir(src)

    # Cache darf kein halb-fertiges Ziel haben
    target = cache.path_for("qualdatan/test", "0.1.0")
    assert not target.exists()
    # kein tmp-Verzeichnis haengen gelassen
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    leftovers = [p for p in parent.iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_remove(make_bundle) -> None:
    src = make_bundle("qualdatan/test", "0.1.0")
    cache = BundleCache()
    cache.install_from_dir(src)
    assert cache.exists("qualdatan/test", "0.1.0")
    cache.remove("qualdatan/test", "0.1.0")
    assert not cache.exists("qualdatan/test", "0.1.0")
    # remove ist idempotent
    cache.remove("qualdatan/test", "0.1.0")


def test_iter_installed(make_bundle, tmp_path: Path) -> None:
    cache = BundleCache()
    cache.install_from_dir(make_bundle("qualdatan/test", "0.1.0", subdir="a"))
    cache.install_from_dir(make_bundle("qualdatan/test", "0.2.0", subdir="b"))
    cache.install_from_dir(make_bundle("qualdatan/other", "1.0.0", subdir="c"))

    ids = sorted((ib.id, ib.version) for ib in cache.iter_installed())
    assert ids == [
        ("qualdatan/other", "1.0.0"),
        ("qualdatan/test", "0.1.0"),
        ("qualdatan/test", "0.2.0"),
    ]


def test_iter_installed_skips_broken_dirs(make_bundle, tmp_path: Path) -> None:
    cache = BundleCache()
    cache.install_from_dir(make_bundle("qualdatan/test", "0.1.0"))
    # stray dir ohne bundle.yaml
    (cache.root / "qualdatan" / "test" / "0.2.0").mkdir(parents=True)
    (cache.root / "randomfile").write_text("x")

    ids = [(ib.id, ib.version) for ib in cache.iter_installed()]
    assert ids == [("qualdatan/test", "0.1.0")]


@pytest.mark.network
def test_install_from_git_uses_subprocess(make_bundle, monkeypatch, tmp_path: Path) -> None:
    """Stubbt git, damit kein Netzwerk benutzt wird."""
    src = make_bundle("qualdatan/test", "0.1.0", subdir="fakeclone")

    captured: list[list[str]] = []

    def fake_run(cmd, check=True, capture_output=True, text=False):
        captured.append(list(cmd))
        if cmd[1] == "clone":
            # clone dest ist das letzte arg: Inhalt von `src` dorthin kopieren
            import shutil
            dest = Path(cmd[-1])
            shutil.copytree(src, dest)
            return mock.Mock(returncode=0, stdout="", stderr="")
        if "rev-parse" in cmd:
            return mock.Mock(returncode=0, stdout="deadbeef\n", stderr="")
        return mock.Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("qualdatan_plugins.cache.subprocess.run", fake_run)
    cache = BundleCache()
    ib = cache.install_from_git("https://example/repo.git", "0.1.0")

    assert ib.source == "git"
    assert ib.origin == "https://example/repo.git"
    assert ib.commit_sha == "deadbeef"
    assert captured[0][:5] == ["git", "clone", "--depth=1", "--branch", "v0.1.0"]
    assert cache.exists("qualdatan/test", "0.1.0")
