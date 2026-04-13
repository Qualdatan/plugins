# SPDX-License-Identifier: AGPL-3.0-only
"""Bundle -> PluginSource Adapter.

:class:`BundleSource` implementiert das
:class:`qualdatan_core.plugins.PluginSource`-Protocol ueber eine Menge
installierter Bundles. Damit reicht der Plugin-Manager die aktiven Bundles
an die Core-Library, ohne dass Core selbst das Bundle-Format kennen muss.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from qualdatan_core.facets import Facet, load_facet_from_yaml, load_facets_from_dir
from qualdatan_core.layouts import FolderLayout

from .bundle import InstalledBundle

_log = logging.getLogger(__name__)

# Felder, die FolderLayout.from_dict tatsaechlich verarbeitet. Alles andere
# (z.B. ``id``, ``label``, ``description`` in der Layout-YAML) wird ignoriert.
_LAYOUT_FIELDS: frozenset[str] = frozenset(
    {
        "folder_prefix",
        "folder_pattern",
        "interviews_subdir",
        "notes_subdir",
        "pdf_ext",
        "interview_exts",
        "office_exts",
    }
)


def load_bundle_facets(ib: InstalledBundle) -> list[Facet]:
    """Laedt alle Facets eines installierten Bundles.

    Jeder Eintrag in ``manifest.facets`` darf entweder eine YAML-Datei oder
    ein Verzeichnis sein; im Verzeichnisfall wird
    :func:`qualdatan_core.facets.load_facets_from_dir` genutzt.

    Args:
        ib: Das installierte Bundle.

    Returns:
        Liste von geladenen :class:`Facet`-Instanzen (in Manifest-Reihenfolge).
    """

    out: list[Facet] = []
    for rel in ib.manifest.facets:
        p = ib.manifest.resolve(rel)
        if p.is_dir():
            out.extend(load_facets_from_dir(p))
        elif p.is_file():
            out.append(load_facet_from_yaml(p))
        else:
            _log.warning("Facet-Pfad existiert nicht: %s (%s)", rel, ib.manifest.ref())
    return out


def _build_layout(data: dict[str, Any], source: str) -> FolderLayout:
    """Baut ein FolderLayout aus einem YAML-Mapping.

    Unbekannte Keys werden ignoriert (mit Debug-Log); tuple-Felder werden
    normalisiert.
    """

    if not isinstance(data, dict):
        raise ValueError(f"Layout-YAML muss Mapping sein: {source}")

    unknown = set(data.keys()) - _LAYOUT_FIELDS
    # Metadata-Keys, die wir bewusst ignorieren, ohne zu warnen:
    silent = {"id", "label", "description"}
    loud_unknown = unknown - silent
    if loud_unknown:
        _log.warning("Layout %s: unbekannte Keys ignoriert: %s", source, sorted(loud_unknown))

    # FolderLayout.from_dict kuemmert sich selbst um tuple-conversion und
    # unbekannte Keys; wir haetten das auch hier machen koennen, aber so
    # bleibt das Verhalten an zentraler Stelle.
    return FolderLayout.from_dict(data)


def load_bundle_layouts(ib: InstalledBundle) -> list[FolderLayout]:
    """Laedt alle Layouts eines installierten Bundles aus YAML.

    Args:
        ib: Das installierte Bundle.

    Returns:
        Liste von :class:`FolderLayout`-Instanzen (in Manifest-Reihenfolge).
    """

    out: list[FolderLayout] = []
    for rel in ib.manifest.layouts:
        p = ib.manifest.resolve(rel)
        if not p.is_file():
            _log.warning("Layout-Pfad existiert nicht: %s (%s)", rel, ib.manifest.ref())
            continue
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        out.append(_build_layout(data, source=str(p)))
    return out


class BundleSource:
    """PluginSource-Adapter ueber eine Sequenz installierter Bundles.

    Nur **aktivierte** Bundles (``enabled=True``) werden in den Iterator-
    Methoden beruecksichtigt; deaktivierte Bundles bleiben aber in der
    :attr:`bundles`-Tuple erhalten, damit der Manager sie auflisten kann.

    Example:
        >>> src = BundleSource([ib1, ib2])
        >>> list(src.iter_facets())
        [...]
    """

    def __init__(self, bundles: Iterable[InstalledBundle]) -> None:
        self._bundles: tuple[InstalledBundle, ...] = tuple(bundles)

    @property
    def bundles(self) -> tuple[InstalledBundle, ...]:
        """Alle Bundles (auch deaktivierte), in Konstruktor-Reihenfolge."""

        return self._bundles

    def _active(self) -> Iterable[InstalledBundle]:
        return (ib for ib in self._bundles if ib.enabled)

    # --- PluginSource protocol -----------------------------------------
    def iter_facets(self) -> Iterable[Facet]:
        """Alle Facets aller aktiven Bundles."""

        for ib in self._active():
            yield from load_bundle_facets(ib)

    def iter_codebook_paths(self) -> Iterable[Path]:
        """Absolute Pfade zu allen Codebooks aller aktiven Bundles."""

        for ib in self._active():
            for rel in ib.manifest.codebooks:
                yield ib.manifest.resolve(rel)

    def iter_method_paths(self) -> Iterable[Path]:
        """Absolute Pfade zu allen Methods aller aktiven Bundles."""

        for ib in self._active():
            for rel in ib.manifest.methods:
                yield ib.manifest.resolve(rel)

    def iter_layouts(self) -> Iterable[FolderLayout]:
        """Alle Layouts aller aktiven Bundles."""

        for ib in self._active():
            yield from load_bundle_layouts(ib)


__all__ = [
    "BundleSource",
    "load_bundle_facets",
    "load_bundle_layouts",
]
