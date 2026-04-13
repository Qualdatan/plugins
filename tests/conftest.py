# SPDX-License-Identifier: AGPL-3.0-only
"""Shared fixtures fuer cache/registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _write_manifest(target: Path, bundle_id: str, version: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "bundle.yaml").write_text(
        yaml.safe_dump(
            {
                "id": bundle_id,
                "version": version,
                "label": "Test Bundle",
                "description": "fixture bundle",
                "author": "tester",
                "homepage": "",
                "license": "AGPL-3.0-only",
                "requires": {"qualdatan-core": ">=0.1,<0.2"},
                "facets": [],
                "codebooks": [],
                "methods": [],
                "layouts": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def make_bundle(tmp_path: Path):
    """Factory: baut ein minimales Bundle-Verzeichnis unter tmp_path."""

    def _factory(
        bundle_id: str = "qualdatan/test",
        version: str = "0.1.0",
        subdir: str = "src",
    ) -> Path:
        target = tmp_path / subdir
        _write_manifest(target, bundle_id, version)
        return target

    return _factory


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Jeder Test bekommt eigene cache- + registry-Pfade."""
    monkeypatch.setenv("QUALDATAN_BUNDLE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("QUALDATAN_PLUGIN_REGISTRY", str(tmp_path / "plugins.db"))
