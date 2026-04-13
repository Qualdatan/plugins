# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer qualdatan_plugins.verify."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qualdatan_plugins.bundle import load_manifest
from qualdatan_plugins.verify import (
    VerificationError,
    hash_bundle,
    verify_installed,
    verify_manifest,
)
from qualdatan_plugins.bundle import InstalledBundle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _write_minimal_bundle(root: Path, *, with_files: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "facets").mkdir(exist_ok=True)
    (root / "codebooks").mkdir(exist_ok=True)
    (root / "methods").mkdir(exist_ok=True)
    (root / "layouts").mkdir(exist_ok=True)

    if with_files:
        (root / "facets" / "f.yaml").write_text("id: x\ntype: taxonomy\nlabel: X\ncodes: []\n")
        (root / "codebooks" / "c.yml").write_text("codes: {}\n")
        (root / "methods" / "m.yaml").write_text("name: m\n")
        (root / "layouts" / "l.yaml").write_text("folder_prefix: projekt\n")

    manifest = {
        "id": "test/fake",
        "version": "0.1.0",
        "label": "Fake",
        "description": "t",
        "author": "t",
        "homepage": "",
        "license": "MIT",
        "requires": {"qualdatan-core": ">=0.1,<0.2"},
        "facets": ["facets/f.yaml"],
        "codebooks": ["codebooks/c.yml"],
        "methods": ["methods/m.yaml"],
        "layouts": ["layouts/l.yaml"],
    }
    (root / "bundle.yaml").write_text(yaml.safe_dump(manifest))
    return root


def _bim_basic_root() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "bundles" / "bim-basic",
        here.parents[4] / "bundles" / "bim-basic",
        Path("/mnt/d/ai/transcript/bundles/bim-basic"),
    ]
    return next((p for p in candidates if (p / "bundle.yaml").is_file()), None)


# ---------------------------------------------------------------------------
# verify_manifest
# ---------------------------------------------------------------------------
class TestVerifyManifest:
    def test_ok_on_valid_bundle(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert rep.ok, rep.errors
        assert rep.errors == ()

    def test_detects_missing_facet_file(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        (root / "facets" / "f.yaml").unlink()
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert not rep.ok
        assert any("facets" in e for e in rep.errors)

    def test_detects_missing_codebook(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        (root / "codebooks" / "c.yml").unlink()
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert not rep.ok
        assert any("codebooks" in e for e in rep.errors)

    def test_warns_on_empty_license(self, tmp_path: Path):
        root = tmp_path / "b"
        _write_minimal_bundle(root)
        data = yaml.safe_load((root / "bundle.yaml").read_text())
        data["license"] = ""
        (root / "bundle.yaml").write_text(yaml.safe_dump(data))
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert rep.ok
        assert any("license" in w for w in rep.warnings)

    def test_missing_qualdatan_core_requires(self, tmp_path: Path):
        root = tmp_path / "b"
        _write_minimal_bundle(root)
        data = yaml.safe_load((root / "bundle.yaml").read_text())
        data["requires"] = {"something-else": ">=1"}
        (root / "bundle.yaml").write_text(yaml.safe_dump(data))
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert not rep.ok
        assert any("qualdatan-core" in e for e in rep.errors)

    def test_bim_basic_bundle_verifies(self):
        root = _bim_basic_root()
        if root is None:
            pytest.skip("bim-basic bundle nicht gefunden")
        m = load_manifest(root)
        rep = verify_manifest(m)
        assert rep.ok, rep.errors


# ---------------------------------------------------------------------------
# verify_installed
# ---------------------------------------------------------------------------
class TestVerifyInstalled:
    def test_ok(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        m = load_manifest(root)
        ib = InstalledBundle(manifest=m, install_path=root, source="local")
        rep = verify_installed(ib)
        assert rep.ok, rep.errors

    def test_install_path_mismatch(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        other = tmp_path / "other"
        other.mkdir()
        m = load_manifest(root)
        ib = InstalledBundle(manifest=m, install_path=other, source="local")
        rep = verify_installed(ib)
        assert not rep.ok
        assert any("install_path" in e for e in rep.errors)


# ---------------------------------------------------------------------------
# hash_bundle
# ---------------------------------------------------------------------------
class TestHashBundle:
    def test_stable_across_runs(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        h1 = hash_bundle(root)
        h2 = hash_bundle(root)
        assert h1 == h2
        assert len(h1) == 64

    def test_changes_when_file_changes(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        h1 = hash_bundle(root)
        (root / "facets" / "f.yaml").write_text("id: y\ntype: taxonomy\nlabel: Y\ncodes: []\n")
        h2 = hash_bundle(root)
        assert h1 != h2

    def test_skips_git_and_pycache(self, tmp_path: Path):
        root = _write_minimal_bundle(tmp_path / "b")
        h1 = hash_bundle(root)
        # Add .git and __pycache__ noise.
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")
        h2 = hash_bundle(root)
        assert h1 == h2

    def test_raises_on_missing_root(self, tmp_path: Path):
        with pytest.raises(VerificationError):
            hash_bundle(tmp_path / "nope")
