# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer qualdatan_plugins.registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from qualdatan_plugins.bundle import BundleError
from qualdatan_plugins.cache import BundleCache
from qualdatan_plugins.registry import PluginRegistry


def _install(cache: BundleCache, make_bundle, bundle_id: str, version: str, subdir: str):
    src = make_bundle(bundle_id, version, subdir=subdir)
    return cache.install_from_dir(src)


def test_db_created_and_schema_versioned(tmp_path: Path) -> None:
    reg = PluginRegistry()
    assert reg.db_path == tmp_path / "plugins.db"
    assert reg.db_path.is_file()

    cur = reg._conn.execute("PRAGMA user_version")
    (version,) = cur.fetchone()
    assert version == 1
    reg.close()


def test_record_and_list_installed(make_bundle) -> None:
    cache = BundleCache()
    ib = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")

    reg = PluginRegistry()
    reg.record_install(ib)

    items = reg.list_installed()
    assert len(items) == 1
    assert items[0].id == "qualdatan/test"
    assert items[0].version == "0.1.0"
    assert items[0].install_path == ib.install_path
    reg.close()


def test_record_install_upsert(make_bundle) -> None:
    cache = BundleCache()
    ib = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")

    reg = PluginRegistry()
    reg.record_install(ib)
    reg.record_install(ib)  # second call must not duplicate
    assert len(reg.list_installed()) == 1
    reg.close()


def test_get_installed_newest(make_bundle) -> None:
    cache = BundleCache()
    ib1 = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")
    ib2 = _install(cache, make_bundle, "qualdatan/test", "0.2.0", "b")

    reg = PluginRegistry()
    reg.record_install(ib1)
    reg.record_install(ib2)

    latest = reg.get_installed("qualdatan/test")
    assert latest is not None
    assert latest.version == "0.2.0"

    exact = reg.get_installed("qualdatan/test", "0.1.0")
    assert exact is not None
    assert exact.version == "0.1.0"

    missing = reg.get_installed("qualdatan/missing")
    assert missing is None
    reg.close()


def test_activate_deactivate(make_bundle) -> None:
    cache = BundleCache()
    ib = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")

    reg = PluginRegistry()
    reg.record_install(ib)
    reg.activate("qualdatan/test", "0.1.0", project_id="proj1")

    actives = reg.list_active("proj1")
    assert [a.manifest.ref() for a in actives] == ["qualdatan/test@0.1.0"]
    # anderes project: leer
    assert reg.list_active("other") == []

    reg.deactivate("qualdatan/test", project_id="proj1")
    assert reg.list_active("proj1") == []
    reg.close()


def test_activate_rejects_unknown(make_bundle) -> None:
    reg = PluginRegistry()
    with pytest.raises(BundleError):
        reg.activate("qualdatan/missing", "9.9.9", project_id="p")
    reg.close()


def test_activate_upsert_same_project(make_bundle) -> None:
    cache = BundleCache()
    ib1 = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")
    ib2 = _install(cache, make_bundle, "qualdatan/test", "0.2.0", "b")

    reg = PluginRegistry()
    reg.record_install(ib1)
    reg.record_install(ib2)
    reg.activate("qualdatan/test", "0.1.0", project_id="p")
    reg.activate("qualdatan/test", "0.2.0", project_id="p")

    actives = reg.list_active("p")
    assert len(actives) == 1
    assert actives[0].version == "0.2.0"
    reg.close()


def test_remove_install_cascades_active(make_bundle) -> None:
    cache = BundleCache()
    ib = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")

    reg = PluginRegistry()
    reg.record_install(ib)
    reg.activate("qualdatan/test", "0.1.0", project_id="p")
    reg.remove_install("qualdatan/test", "0.1.0")

    assert reg.list_installed() == []
    assert reg.list_active("p") == []
    reg.close()


def test_reopen_persists_state(make_bundle) -> None:
    cache = BundleCache()
    ib = _install(cache, make_bundle, "qualdatan/test", "0.1.0", "a")

    reg = PluginRegistry()
    reg.record_install(ib)
    reg.activate("qualdatan/test", "0.1.0", project_id="p")
    reg.close()

    reg2 = PluginRegistry()
    assert [x.manifest.ref() for x in reg2.list_installed()] == [
        "qualdatan/test@0.1.0"
    ]
    assert len(reg2.list_active("p")) == 1
    reg2.close()
