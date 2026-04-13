# SPDX-License-Identifier: AGPL-3.0-only
"""Qualdatan plugin manager.

Verwaltet Community-Bundles — YAML-Daten-Pakete mit Facets, Codebooks,
Methoden und Ordner-Layouts fuer konkrete Analyse-Domaenen.

Module
------
- :mod:`.bundle`         Manifest-Datentypen + YAML-Loader
- :mod:`.cache`          Filesystem-Cache fuer installierte Bundles
- :mod:`.registry`       SQLite-Index + per-Projekt-Aktivierung
- :mod:`.loader`         :class:`BundleSource` (erfuellt
  :class:`qualdatan_core.PluginSource`)
- :mod:`.verify`         Manifest- und Integritaets-Checks
- :mod:`.server_client`  HTTP-Client fuer den Tap-Style Plugin-Server
- :mod:`.manager`        :class:`PluginManager` — High-Level-Orchestrator

Vgl. den Gesamtplan:
https://github.com/GeneralPawz/Qualdatan
"""

from .bundle import (
    BundleError,
    BundleManifest,
    BundleRequirement,
    InstalledBundle,
    load_manifest,
    parse_manifest,
)
from .cache import BundleCache
from .loader import BundleSource, load_bundle_facets, load_bundle_layouts
from .manager import InstallResult, PluginManager, PluginManagerError
from .registry import PluginRegistry
from .server_client import (
    PluginServerClient,
    PluginServerError,
    TapEntry,
    TapVersion,
)
from .verify import VerificationReport, hash_bundle, verify_installed, verify_manifest

__version__ = "0.1.0"

__all__ = [
    "BundleError",
    "BundleManifest",
    "BundleRequirement",
    "InstalledBundle",
    "load_manifest",
    "parse_manifest",
    "BundleCache",
    "PluginRegistry",
    "BundleSource",
    "load_bundle_facets",
    "load_bundle_layouts",
    "VerificationReport",
    "hash_bundle",
    "verify_installed",
    "verify_manifest",
    "PluginServerClient",
    "PluginServerError",
    "TapEntry",
    "TapVersion",
    "InstallResult",
    "PluginManager",
    "PluginManagerError",
    "__version__",
]
