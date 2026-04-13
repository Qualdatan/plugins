# SPDX-License-Identifier: AGPL-3.0-only
"""Manifest- und Integritaets-Checks fuer Bundles.

Dieses Modul stellt drei Funktionen bereit, die der Plugin-Manager nach
dem Installieren / vor dem Aktivieren eines Bundles aufruft:

- :func:`verify_manifest` prueft, dass alle im Manifest gelisteten Dateien
  existieren und die ``requires``-Deklaration wohlgeformt ist.
- :func:`verify_installed` ergaenzt das um Pfad-Checks am installierten
  Bundle.
- :func:`hash_bundle` liefert einen deterministischen SHA-256 ueber alle
  Bundle-Dateien (ohne ``.git/`` und ``__pycache__/``) und dient der
  Integritaets-Pruefung.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .bundle import BundleManifest, InstalledBundle

_BUNDLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9_.-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([-.+][0-9A-Za-z.-]+)?$")

_SKIP_DIRS = {".git", "__pycache__"}


class VerificationError(ValueError):
    """Fehler bei einer Verify-Operation."""


@dataclass(frozen=True)
class VerificationReport:
    """Ergebnis eines Verify-Laufs.

    Attributes:
        ok: ``True`` wenn keine Fehler aufgetreten sind.
        errors: Liste von Fehler-Meldungen (ok=False wenn nicht leer).
        warnings: Nicht-blockierende Hinweise.
    """

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _check_paths(
    root: Path,
    rels: tuple[str, ...],
    kind: str,
    errors: list[str],
) -> None:
    for rel in rels:
        p = (root / rel).resolve()
        if not p.exists():
            errors.append(f"{kind}-Pfad existiert nicht: {rel}")


def verify_manifest(manifest: BundleManifest) -> VerificationReport:
    """Prueft das Manifest gegen das Dateisystem.

    Args:
        manifest: Geparstes Manifest (typischerweise aus
            :func:`qualdatan_plugins.bundle.load_manifest`).

    Returns:
        Ein :class:`VerificationReport` mit Fehlern/Warnungen.
    """

    errors: list[str] = []
    warnings: list[str] = []

    # id / version format double-check (bundle.py enforces id at parse time,
    # aber hier haerten wir auch version ab).
    if not _BUNDLE_ID_RE.match(manifest.id):
        errors.append(f"ungueltige bundle-id: {manifest.id!r}")
    if not _SEMVER_RE.match(manifest.version):
        errors.append(f"ungueltige version: {manifest.version!r}")

    # referenzierte Pfade
    _check_paths(manifest.root, manifest.facets, "facets", errors)
    _check_paths(manifest.root, manifest.codebooks, "codebooks", errors)
    _check_paths(manifest.root, manifest.methods, "methods", errors)
    _check_paths(manifest.root, manifest.layouts, "layouts", errors)

    # requires
    core_req = [r for r in manifest.requires if r.package == "qualdatan-core"]
    if not core_req:
        errors.append("requires.qualdatan-core fehlt")
    else:
        spec = core_req[0].version_spec
        if not spec or not isinstance(spec, str):
            errors.append(f"requires.qualdatan-core version_spec leer: {spec!r}")

    # license
    if not manifest.license.strip():
        warnings.append("license ist leer")

    return VerificationReport(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))


def verify_installed(ib: InstalledBundle) -> VerificationReport:
    """Wie :func:`verify_manifest`, plus Pfad-Checks am Install-Verzeichnis.

    Args:
        ib: Das installierte Bundle.

    Returns:
        Ein kombiniertes :class:`VerificationReport`.
    """

    base = verify_manifest(ib.manifest)
    errors = list(base.errors)
    warnings = list(base.warnings)

    if not ib.install_path.exists():
        errors.append(f"install_path existiert nicht: {ib.install_path}")
    else:
        try:
            same = ib.install_path.resolve() == ib.manifest.root.resolve()
        except OSError as e:
            same = False
            errors.append(f"install_path nicht aufloesbar: {e}")
        if not same:
            errors.append(
                f"install_path != manifest.root ({ib.install_path} vs {ib.manifest.root})"
            )

    return VerificationReport(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))


def _iter_bundle_files(root: Path) -> list[Path]:
    """Alle Dateien unter ``root``, deterministisch sortiert, ohne Skip-Dirs."""

    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        # Skip wenn ein Segment des relativen Pfades in _SKIP_DIRS liegt.
        rel_parts = p.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        out.append(p)
    return sorted(out, key=lambda q: q.relative_to(root).as_posix())


def hash_bundle(root: Path) -> str:
    """Berechnet einen deterministischen SHA-256 ueber alle Bundle-Dateien.

    Der Hash wird ueber ``(relpath_bytes + b"\\0" + file_bytes + b"\\0")`` pro
    Datei in sortierter Reihenfolge aufgebaut. ``.git/`` und ``__pycache__/``
    werden ausgeklammert.

    Args:
        root: Bundle-Wurzel.

    Returns:
        Hex-Digest.

    Raises:
        VerificationError: wenn ``root`` nicht existiert.
    """

    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise VerificationError(f"Bundle-root existiert nicht: {root}")

    h = hashlib.sha256()
    for f in _iter_bundle_files(root):
        rel = f.relative_to(root).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


__all__ = [
    "VerificationError",
    "VerificationReport",
    "verify_manifest",
    "verify_installed",
    "hash_bundle",
]
