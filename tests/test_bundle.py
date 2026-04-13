# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer qualdatan_plugins.bundle (Manifest-Parser + Datentypen)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qualdatan_plugins.bundle import (
    BundleError,
    BundleManifest,
    InstalledBundle,
    load_manifest,
    parse_manifest,
)


def _minimal(**overrides):
    data = {
        "id": "qualdatan/test",
        "version": "0.1.0",
        "label": "Test",
        "description": "Minimal",
        "license": "CC-BY-NC-SA-4.0",
    }
    data.update(overrides)
    return data


class TestParseManifest:
    def test_minimal(self, tmp_path: Path):
        m = parse_manifest(_minimal(), tmp_path)
        assert m.id == "qualdatan/test"
        assert m.namespace == "qualdatan"
        assert m.name == "test"
        assert m.version == "0.1.0"
        assert m.ref() == "qualdatan/test@0.1.0"
        assert m.root == tmp_path.resolve()

    def test_rejects_missing_id(self, tmp_path: Path):
        with pytest.raises(BundleError, match="ungueltige bundle-id"):
            parse_manifest({"version": "0.1.0"}, tmp_path)

    def test_rejects_bad_id_format(self, tmp_path: Path):
        with pytest.raises(BundleError):
            parse_manifest(_minimal(id="NoSlash"), tmp_path)

    def test_rejects_uppercase(self, tmp_path: Path):
        with pytest.raises(BundleError):
            parse_manifest(_minimal(id="Qualdatan/Bim"), tmp_path)

    def test_rejects_missing_version(self, tmp_path: Path):
        with pytest.raises(BundleError, match="version"):
            parse_manifest({"id": "qualdatan/test"}, tmp_path)

    def test_list_fields_string_form(self, tmp_path: Path):
        data = _minimal(
            facets=["facets/a.yaml", "facets/b.yaml"],
            codebooks=["codebooks/x.yml"],
        )
        m = parse_manifest(data, tmp_path)
        assert m.facets == ("facets/a.yaml", "facets/b.yaml")
        assert m.codebooks == ("codebooks/x.yml",)

    def test_list_fields_dict_form(self, tmp_path: Path):
        data = _minimal(facets=[{"file": "facets/a.yaml"}])
        m = parse_manifest(data, tmp_path)
        assert m.facets == ("facets/a.yaml",)

    def test_requires(self, tmp_path: Path):
        data = _minimal(requires={"qualdatan-core": ">=0.1,<0.2"})
        m = parse_manifest(data, tmp_path)
        assert len(m.requires) == 1
        assert m.requires[0].package == "qualdatan-core"
        assert m.requires[0].version_spec == ">=0.1,<0.2"

    def test_resolve(self, tmp_path: Path):
        m = parse_manifest(_minimal(), tmp_path)
        assert m.resolve("facets/a.yaml") == (tmp_path / "facets" / "a.yaml").resolve()


class TestLoadManifest:
    def test_from_disk(self, tmp_path: Path):
        (tmp_path / "bundle.yaml").write_text(
            yaml.safe_dump(_minimal(facets=["facets/a.yaml"])),
            encoding="utf-8",
        )
        m = load_manifest(tmp_path)
        assert m.id == "qualdatan/test"
        assert m.facets == ("facets/a.yaml",)

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(BundleError, match="nicht gefunden"):
            load_manifest(tmp_path)

    def test_real_bim_basic(self):
        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "bundles" / "bim-basic",
            here.parents[4] / "bundles" / "bim-basic",
            Path("/mnt/d/ai/transcript/bundles/bim-basic"),
        ]
        root = next((p for p in candidates if (p / "bundle.yaml").exists()), None)
        if root is None:
            pytest.skip("bim-basic bundle nicht gefunden")
        m = load_manifest(root)
        assert m.id == "qualdatan/bim-basic"
        assert m.version
        assert len(m.facets) == 2
        assert len(m.codebooks) == 3
        assert len(m.methods) == 7
        assert len(m.layouts) == 1


class TestInstalledBundle:
    def test_properties(self, tmp_path: Path):
        m = parse_manifest(_minimal(), tmp_path)
        ib = InstalledBundle(
            manifest=m, install_path=tmp_path, source="local",
            origin=str(tmp_path), commit_sha="", enabled=True,
        )
        assert ib.id == "qualdatan/test"
        assert ib.version == "0.1.0"
