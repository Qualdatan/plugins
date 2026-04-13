# SPDX-License-Identifier: AGPL-3.0-only
"""Filesystem-Cache fuer installierte Bundles.

Layout auf Platte::

    <cache_root>/
      <namespace>/
        <name>/
          <version>/        # bundle.yaml + payload

Der Cache-Root wird via :mod:`platformdirs` bestimmt und kann durch die
Umgebungsvariable ``QUALDATAN_BUNDLE_CACHE`` ueberschrieben werden.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

from platformdirs import user_data_dir

from .bundle import (
    BundleError,
    InstalledBundle,
    load_manifest,
)


_ENV_CACHE = "QUALDATAN_BUNDLE_CACHE"


def _default_cache_root() -> Path:
    env = os.environ.get(_ENV_CACHE)
    if env:
        return Path(env)
    return Path(user_data_dir("Qualdatan", "Qualdatan")) / "bundles"


def _split_id(bundle_id: str) -> tuple[str, str]:
    if "/" not in bundle_id:
        raise BundleError(f"ungueltige bundle-id '{bundle_id}'")
    ns, name = bundle_id.split("/", 1)
    return ns, name


class BundleCache:
    """Verwaltet Bundle-Dateien im lokalen Cache-Verzeichnis.

    Die Klasse kapselt Kopier-, Git-Clone- und Remove-Operationen und
    kennt keine Registry-Datenbank; Aktivierungs-State lebt in
    :class:`~qualdatan_plugins.registry.PluginRegistry`.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else _default_cache_root()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Wurzelverzeichnis des Caches."""
        return self._root

    def path_for(self, bundle_id: str, version: str) -> Path:
        """Zielpfad fuer ein konkretes Bundle (kann noch nicht existieren)."""
        ns, name = _split_id(bundle_id)
        return self._root / ns / name / version

    def exists(self, bundle_id: str, version: str) -> bool:
        """True, wenn das Bundle bereits im Cache liegt."""
        target = self.path_for(bundle_id, version)
        return target.is_dir() and (target / "bundle.yaml").is_file()

    # ------------------------------------------------------------------
    # Install / remove
    # ------------------------------------------------------------------
    def install_from_dir(
        self,
        src: Path,
        *,
        expected_id: str | None = None,
    ) -> InstalledBundle:
        """Kopiert ein Bundle aus einem lokalen Verzeichnis in den Cache.

        Args:
            src: Verzeichnis mit ``bundle.yaml`` am Root.
            expected_id: wenn gesetzt, muss die Manifest-Id exakt matchen.

        Returns:
            :class:`InstalledBundle` mit ``source="local"``.

        Raises:
            BundleError: Manifest fehlt/invalide oder ``expected_id`` mismatch.
        """
        src = Path(src).resolve()
        manifest = load_manifest(src)
        if expected_id is not None and manifest.id != expected_id:
            raise BundleError(
                f"bundle-id mismatch: manifest={manifest.id}, erwartet={expected_id}"
            )
        target = self.path_for(manifest.id, manifest.version)
        target.parent.mkdir(parents=True, exist_ok=True)

        # atomarer Swap: erst in tmp-Nachbarverzeichnis kopieren, dann replace
        tmp_parent = target.parent
        tmp_dir = Path(tempfile.mkdtemp(prefix=f".tmp-{manifest.name}-", dir=tmp_parent))
        staging = tmp_dir / "stage"
        try:
            shutil.copytree(src, staging)
            if target.exists():
                # existierenden Install entfernen (Re-Install / Overwrite)
                shutil.rmtree(target)
            os.replace(staging, target)
        except Exception:
            # cleanup auf Fehler
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        finally:
            # tmp_dir nur entfernen, wenn leer (staging wurde wegverschoben)
            try:
                tmp_dir.rmdir()
            except OSError:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        installed_manifest = load_manifest(target)
        return InstalledBundle(
            manifest=installed_manifest,
            install_path=target,
            source="local",
            origin=str(src),
        )

    def install_from_git(
        self,
        repo_url: str,
        version: str,
        *,
        commit_sha: str = "",
    ) -> InstalledBundle:
        """Klont ein Git-Repo (Tag ``v<version>``) und installiert daraus.

        Args:
            repo_url: Git-URL (z.B. ``https://github.com/org/bundle.git``).
            version: Semver ohne ``v``-Prefix; der Tag heisst ``v<version>``.
            commit_sha: optional; wird in :class:`InstalledBundle` gespeichert,
                falls der Aufrufer einen bereits verifizierten SHA hat. Wird
                nicht angegeben, liest die Methode ``git rev-parse HEAD``.

        Returns:
            :class:`InstalledBundle` mit ``source="git"``.
        """
        with tempfile.TemporaryDirectory(prefix="qualdatan-git-") as tmp:
            tmp_path = Path(tmp) / "clone"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--branch",
                    f"v{version}",
                    repo_url,
                    str(tmp_path),
                ],
                check=True,
                capture_output=True,
            )
            if not commit_sha:
                result = subprocess.run(
                    ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                commit_sha = result.stdout.strip()

            local = self.install_from_dir(tmp_path)

        return InstalledBundle(
            manifest=local.manifest,
            install_path=local.install_path,
            source="git",
            origin=repo_url,
            commit_sha=commit_sha,
        )

    def remove(self, bundle_id: str, version: str) -> None:
        """Loescht ein Bundle aus dem Cache (no-op wenn nicht vorhanden)."""
        target = self.path_for(bundle_id, version)
        if target.exists():
            shutil.rmtree(target)
        # leere Parent-Verzeichnisse aufraeumen
        parent = target.parent
        for _ in range(2):  # name/, namespace/
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def iter_installed(self) -> Iterable[InstalledBundle]:
        """Walked den Cache und liefert alle valide geparsten Bundles."""
        if not self._root.is_dir():
            return
        for ns_dir in sorted(self._root.iterdir()):
            if not ns_dir.is_dir():
                continue
            for name_dir in sorted(ns_dir.iterdir()):
                if not name_dir.is_dir():
                    continue
                for version_dir in sorted(name_dir.iterdir()):
                    if not version_dir.is_dir():
                        continue
                    if not (version_dir / "bundle.yaml").is_file():
                        continue
                    try:
                        manifest = load_manifest(version_dir)
                    except BundleError:
                        continue
                    yield InstalledBundle(
                        manifest=manifest,
                        install_path=version_dir,
                        source="local",
                        origin=str(version_dir),
                    )


__all__ = ["BundleCache"]
