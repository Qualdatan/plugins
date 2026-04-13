# SPDX-License-Identifier: AGPL-3.0-only
"""High-Level-Orchestrator fuer den Qualdatan Plugin-Manager.

Fasst :class:`BundleCache`, :class:`PluginRegistry`, den YAML-Loader und den
Verifikator zu einer einzigen API zusammen, wie sie TUI und Sidecar benutzen.

Typischer Lebenszyklus::

    mgr = PluginManager()
    mgr.install_from_path(Path("./bundles/bim-basic"))
    mgr.activate("qualdatan/bim-basic", project_id="my-project")
    source = mgr.source_for("my-project")        # PluginSource fuer Core
    for facet in source.iter_facets():
        ...
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .bundle import BundleError, InstalledBundle, load_manifest
from .cache import BundleCache
from .loader import BundleSource
from .registry import PluginRegistry
from .verify import VerificationReport, verify_installed, verify_manifest


class PluginManagerError(RuntimeError):
    """Fehler auf Manager-Ebene (Install/Activate/Verify)."""


@dataclass(frozen=True)
class InstallResult:
    """Ergebnis einer Install-Operation."""

    bundle: InstalledBundle
    verification: VerificationReport


class PluginManager:
    """Koordiniert Cache, Registry, Loader und Verify.

    Args:
        cache: optionaler :class:`BundleCache`; Default nutzt Env/platformdirs.
        registry: optionale :class:`PluginRegistry`; Default nutzt Env/platformdirs.
        verify_on_install: wenn ``True`` (Default), schlaegt install fehl,
            falls das Manifest Integritaetsprobleme hat.
    """

    def __init__(
        self,
        cache: BundleCache | None = None,
        registry: PluginRegistry | None = None,
        *,
        verify_on_install: bool = True,
    ) -> None:
        self._cache = cache or BundleCache()
        self._registry = registry or PluginRegistry()
        self._verify_on_install = verify_on_install

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._registry.close()

    def __enter__(self) -> "PluginManager":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def cache(self) -> BundleCache:
        return self._cache

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    # ------------------------------------------------------------------
    # Install / Update / Remove
    # ------------------------------------------------------------------
    def install_from_path(
        self, src: Path, *, expected_id: str | None = None
    ) -> InstallResult:
        """Installiert ein lokales Bundle-Verzeichnis.

        Args:
            src: Ordner mit ``bundle.yaml`` im Wurzelverzeichnis.
            expected_id: optional; wenn gesetzt, muss die Manifest-Id matchen.

        Returns:
            :class:`InstallResult` mit dem registrierten :class:`InstalledBundle`
            und dem Verifikations-Report.

        Raises:
            PluginManagerError: wenn Verifikation mit ``verify_on_install=True``
                fehlschlaegt.
        """

        ib = self._cache.install_from_dir(src, expected_id=expected_id)
        return self._finalize_install(ib)

    def install_from_git(
        self, repo_url: str, version: str, *, commit_sha: str = ""
    ) -> InstallResult:
        """Installiert ein Bundle via ``git clone --depth=1 --branch=v<version>``."""

        ib = self._cache.install_from_git(repo_url, version, commit_sha=commit_sha)
        return self._finalize_install(ib)

    def _finalize_install(self, ib: InstalledBundle) -> InstallResult:
        report = verify_installed(ib)
        if self._verify_on_install and not report.ok:
            # Rollback: den frisch kopierten Cache-Eintrag entfernen.
            try:
                self._cache.remove(ib.id, ib.version)
            except Exception:
                pass
            raise PluginManagerError(
                f"Verifikation fuer {ib.manifest.ref()} fehlgeschlagen: "
                + "; ".join(report.errors)
            )
        self._registry.record_install(ib)
        return InstallResult(bundle=ib, verification=report)

    def uninstall(self, bundle_id: str, version: str | None = None) -> None:
        """Entfernt ein installiertes Bundle (Cache + Registry).

        Ohne ``version`` wird die aktuell registrierte Version entfernt.
        """

        ib = self._registry.get_installed(bundle_id, version)
        if ib is None:
            raise PluginManagerError(f"Bundle '{bundle_id}' ist nicht installiert")
        self._registry.remove_install(ib.id, ib.version)
        try:
            self._cache.remove(ib.id, ib.version)
        except BundleError:
            # Cache-Eintrag war evtl. schon weg — kein harter Fehler.
            pass

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_installed(self) -> list[InstalledBundle]:
        return self._registry.list_installed()

    def list_active(self, project_id: str = "") -> list[InstalledBundle]:
        return self._registry.list_active(project_id)

    def verify(self, bundle_id: str, version: str | None = None) -> VerificationReport:
        ib = self._registry.get_installed(bundle_id, version)
        if ib is None:
            raise PluginManagerError(f"Bundle '{bundle_id}' ist nicht installiert")
        return verify_installed(ib)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------
    def activate(
        self, bundle_id: str, *, project_id: str = "", version: str | None = None
    ) -> InstalledBundle:
        ib = self._registry.get_installed(bundle_id, version)
        if ib is None:
            raise PluginManagerError(
                f"Bundle '{bundle_id}' ist nicht installiert "
                f"(Version {version or 'latest'})"
            )
        self._registry.activate(ib.id, ib.version, project_id=project_id)
        return ib

    def deactivate(self, bundle_id: str, *, project_id: str = "") -> None:
        self._registry.deactivate(bundle_id, project_id=project_id)

    # ------------------------------------------------------------------
    # Consumption: liefert den PluginSource fuer Core
    # ------------------------------------------------------------------
    def source_for(self, project_id: str = "") -> BundleSource:
        """Baut einen :class:`BundleSource` aus den aktiven Bundles.

        Wenn fuer ein Projekt nichts aktiv ist, faellt die Methode auf den
        globalen Default (``project_id=""``) zurueck.
        """

        active = self._registry.list_active(project_id)
        if not active and project_id:
            active = self._registry.list_active("")
        return BundleSource(active)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def discover_local(self, root: Path) -> list[Path]:
        """Findet Bundle-Wurzeln unter ``root`` (rekursiv, 2 Ebenen).

        Ein Ordner gilt als Bundle, wenn er eine ``bundle.yaml`` enthaelt.
        """

        root = Path(root)
        if not root.exists():
            return []
        found: list[Path] = []
        if (root / "bundle.yaml").is_file():
            found.append(root)
        for child in sorted(root.iterdir()) if root.is_dir() else ():
            if child.is_dir() and (child / "bundle.yaml").is_file():
                found.append(child)
        return found


__all__ = [
    "PluginManager",
    "PluginManagerError",
    "InstallResult",
]
