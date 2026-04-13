# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer qualdatan_plugins.loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from qualdatan_core.facets import Facet
from qualdatan_core.layouts import FolderLayout
from qualdatan_core.plugins import PluginSource

from qualdatan_plugins.bundle import InstalledBundle, load_manifest
from qualdatan_plugins.loader import (
    BundleSource,
    load_bundle_facets,
    load_bundle_layouts,
)


def _bim_basic_root() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "bundles" / "bim-basic",
        here.parents[4] / "bundles" / "bim-basic",
        Path("/mnt/d/ai/transcript/bundles/bim-basic"),
    ]
    return next((p for p in candidates if (p / "bundle.yaml").is_file()), None)


@pytest.fixture
def bim_basic_installed() -> InstalledBundle:
    root = _bim_basic_root()
    if root is None:
        pytest.skip("bim-basic bundle nicht gefunden")
    m = load_manifest(root)
    return InstalledBundle(manifest=m, install_path=root, source="local")


class TestBundleSourceProtocol:
    def test_satisfies_plugin_source(self):
        src = BundleSource([])
        assert isinstance(src, PluginSource)

    def test_bundles_property_preserves_order(self, bim_basic_installed: InstalledBundle):
        src = BundleSource([bim_basic_installed])
        assert src.bundles == (bim_basic_installed,)


class TestLoadBundleFacets:
    def test_bim_basic_has_two_facets(self, bim_basic_installed: InstalledBundle):
        facets = load_bundle_facets(bim_basic_installed)
        ids = sorted(f.id for f in facets)
        assert ids == ["ifc-elements", "log-evidence"]
        for f in facets:
            assert isinstance(f, Facet)


class TestLoadBundleLayouts:
    def test_bim_basic_layout_loads(self, bim_basic_installed: InstalledBundle):
        layouts = load_bundle_layouts(bim_basic_installed)
        assert len(layouts) == 1
        assert isinstance(layouts[0], FolderLayout)
        assert layouts[0].folder_prefix == "projekt"
        assert layouts[0].interviews_subdir == "interviews"
        assert layouts[0].notes_subdir == "sonstiges"


class TestBundleSourceIteration:
    def test_iter_facets_count(self, bim_basic_installed: InstalledBundle):
        src = BundleSource([bim_basic_installed])
        facets = list(src.iter_facets())
        assert len(facets) == 2

    def test_iter_codebook_paths(self, bim_basic_installed: InstalledBundle):
        src = BundleSource([bim_basic_installed])
        paths = list(src.iter_codebook_paths())
        assert len(paths) == 3
        for p in paths:
            assert p.is_file(), p

    def test_iter_method_paths(self, bim_basic_installed: InstalledBundle):
        src = BundleSource([bim_basic_installed])
        paths = list(src.iter_method_paths())
        assert len(paths) == 7
        for p in paths:
            assert p.is_file(), p

    def test_iter_layouts(self, bim_basic_installed: InstalledBundle):
        src = BundleSource([bim_basic_installed])
        layouts = list(src.iter_layouts())
        assert len(layouts) == 1
        assert isinstance(layouts[0], FolderLayout)

    def test_disabled_bundle_yields_nothing(self, bim_basic_installed: InstalledBundle):
        disabled = InstalledBundle(
            manifest=bim_basic_installed.manifest,
            install_path=bim_basic_installed.install_path,
            source="local",
            enabled=False,
        )
        src = BundleSource([disabled])
        assert list(src.iter_facets()) == []
        assert list(src.iter_codebook_paths()) == []
        assert list(src.iter_method_paths()) == []
        assert list(src.iter_layouts()) == []
        # still listed:
        assert src.bundles == (disabled,)
