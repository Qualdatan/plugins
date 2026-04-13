# SPDX-License-Identifier: AGPL-3.0-only
"""Integrationstests fuer :class:`PluginManager`."""

from __future__ import annotations

from pathlib import Path

import pytest

from qualdatan_core.plugins import PluginSource
from qualdatan_plugins.bundle import load_manifest
from qualdatan_plugins.manager import (
    InstallResult,
    PluginManager,
    PluginManagerError,
)


class TestInstallFromPath:
    def test_roundtrip(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo", version="0.1.0")
        with PluginManager() as mgr:
            result = mgr.install_from_path(src)
            assert isinstance(result, InstallResult)
            assert result.verification.ok
            assert result.bundle.id == "qualdatan/foo"
            ids = [b.id for b in mgr.list_installed()]
            assert "qualdatan/foo" in ids

    def test_expected_id_mismatch(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            with pytest.raises(Exception):
                mgr.install_from_path(src, expected_id="qualdatan/bar")

    def test_verify_rollback_removes_cache(self, tmp_path, make_bundle, monkeypatch):
        src = make_bundle(bundle_id="qualdatan/foo")
        # Sabotage: verify_installed returniert immer ok=False.
        from qualdatan_plugins import manager as mgr_mod

        def bad_verify(ib):
            from qualdatan_plugins.verify import VerificationReport
            return VerificationReport(ok=False, errors=("forced fail",), warnings=())

        monkeypatch.setattr(mgr_mod, "verify_installed", bad_verify)
        with PluginManager() as mgr:
            with pytest.raises(PluginManagerError, match="Verifikation"):
                mgr.install_from_path(src)
            assert mgr.list_installed() == []


class TestActivation:
    def test_activate_and_source(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            mgr.install_from_path(src)
            mgr.activate("qualdatan/foo", project_id="p1")
            active = mgr.list_active("p1")
            assert [b.id for b in active] == ["qualdatan/foo"]
            source = mgr.source_for("p1")
            assert isinstance(source, PluginSource)
            assert list(source.iter_facets()) == []  # leeres Fixture-Bundle

    def test_source_falls_back_to_global(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            mgr.install_from_path(src)
            mgr.activate("qualdatan/foo")  # global
            source = mgr.source_for("other-project")
            assert [b.id for b in source.bundles] == ["qualdatan/foo"]

    def test_deactivate(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            mgr.install_from_path(src)
            mgr.activate("qualdatan/foo", project_id="p1")
            mgr.deactivate("qualdatan/foo", project_id="p1")
            assert mgr.list_active("p1") == []

    def test_activate_unknown_raises(self):
        with PluginManager() as mgr:
            with pytest.raises(PluginManagerError, match="nicht installiert"):
                mgr.activate("qualdatan/missing")


class TestUninstall:
    def test_removes_from_cache_and_registry(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            mgr.install_from_path(src)
            mgr.uninstall("qualdatan/foo")
            assert mgr.list_installed() == []
            assert not mgr.cache.exists("qualdatan/foo", "0.1.0")

    def test_uninstall_unknown(self):
        with PluginManager() as mgr:
            with pytest.raises(PluginManagerError):
                mgr.uninstall("qualdatan/missing")


class TestDiscoverLocal:
    def test_discovers_bim_basic(self):
        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "bundles",
            here.parents[4] / "bundles",
            Path("/mnt/d/ai/transcript/bundles"),
        ]
        root = next((p for p in candidates if p.exists()), None)
        if root is None:
            pytest.skip("bundles dir nicht gefunden")
        with PluginManager() as mgr:
            found = mgr.discover_local(root)
        assert any(p.name == "bim-basic" for p in found)

    def test_single_bundle_root(self, make_bundle):
        src = make_bundle(bundle_id="qualdatan/foo")
        with PluginManager() as mgr:
            found = mgr.discover_local(src)
        assert found == [src]


class TestBimBasicEndToEnd:
    def test_install_activate_consume(self, tmp_path):
        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "bundles" / "bim-basic",
            here.parents[4] / "bundles" / "bim-basic",
            Path("/mnt/d/ai/transcript/bundles/bim-basic"),
        ]
        src = next((p for p in candidates if (p / "bundle.yaml").exists()), None)
        if src is None:
            pytest.skip("bim-basic bundle nicht gefunden")

        with PluginManager() as mgr:
            result = mgr.install_from_path(src)
            assert result.verification.ok
            mgr.activate(result.bundle.id)
            source = mgr.source_for()
            facets = list(source.iter_facets())
            layouts = list(source.iter_layouts())
            codebooks = list(source.iter_codebook_paths())
            methods = list(source.iter_method_paths())
        assert len(facets) == 2
        assert len(layouts) == 1
        assert len(codebooks) == 3
        assert len(methods) == 7
