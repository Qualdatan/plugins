# SPDX-License-Identifier: AGPL-3.0-only
"""Bundle-Datentypen und Manifest-Loader.

Ein Bundle ist ein YAML-Daten-Paket mit Facets, Codebooks, Methoden und
Folder-Layouts fuer eine konkrete Domaene. Es wird durch eine ``bundle.yaml``
im Wurzelverzeichnis identifiziert.

Bundle-Id folgt dem Schema ``namespace/name`` (z.B. ``qualdatan/bim-basic``).
``namespace`` ist typischerweise ein GitHub-User oder eine -Org; der
Plugin-Server verifiziert die Besitzerschaft via GitHub-OAuth.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_BUNDLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9_.-]*$")


class BundleError(ValueError):
    """Fehler beim Laden / Validieren eines Bundles."""


@dataclass(frozen=True)
class BundleRequirement:
    """Eine Paketabhaengigkeit im Bundle-Manifest (``requires``-Sektion)."""

    package: str
    version_spec: str  # z.B. ">=0.1,<0.2"


@dataclass(frozen=True)
class BundleManifest:
    """Parsed ``bundle.yaml``.

    Pfade in ``facets``/``codebooks``/``methods``/``layouts`` sind relativ
    zu ``root``; Konsumenten koennen ``manifest.resolve(p)`` benutzen.
    """

    id: str                       # "namespace/name"
    version: str                  # Semver-String "0.1.0"
    label: str
    description: str
    author: str
    homepage: str
    license: str
    requires: tuple[BundleRequirement, ...]
    facets: tuple[str, ...]       # relative paths
    codebooks: tuple[str, ...]
    methods: tuple[str, ...]
    layouts: tuple[str, ...]
    root: Path                    # absolut, enthaelt ``bundle.yaml``

    @property
    def namespace(self) -> str:
        return self.id.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.id.split("/", 1)[1]

    def resolve(self, rel: str) -> Path:
        """Absoluter Pfad zu einer im Manifest genannten Datei."""
        return (self.root / rel).resolve()

    def ref(self) -> str:
        """Bundle-Referenz ``namespace/name@version``."""
        return f"{self.id}@{self.version}"


@dataclass(frozen=True)
class InstalledBundle:
    """Ein installiertes Bundle im lokalen Cache.

    ``source`` beschreibt, woher das Bundle kam (``"local"``, ``"git"``,
    ``"zip"``). ``commit_sha`` ist bei Git-Installs gesetzt und erlaubt es
    dem Registry-Server, Integritaet gegen den GitHub-Commit zu pruefen.
    """

    manifest: BundleManifest
    install_path: Path
    source: str
    origin: str = ""             # repo-url, zip-path, local-dir
    commit_sha: str = ""
    enabled: bool = True

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _validate_id(value: Any) -> str:
    if not isinstance(value, str) or not _BUNDLE_ID_RE.match(value):
        raise BundleError(
            f"ungueltige bundle-id '{value}': erwartet 'namespace/name' "
            f"(lowercase, alphanumerisch + '-._')"
        )
    return value


def _as_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BundleError(f"'{field_name}' muss eine YAML-Liste sein")
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, Mapping) and "file" in item:
            # Kompatibilitaet: "{ file: path }"-Form
            out.append(str(item["file"]))
        else:
            raise BundleError(
                f"'{field_name}' Eintrag muss String oder {{file: ...}} sein, "
                f"bekam: {item!r}"
            )
    return tuple(out)


def _parse_requires(value: Any) -> tuple[BundleRequirement, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise BundleError("'requires' muss ein YAML-Mapping sein (pkg -> spec)")
    return tuple(
        BundleRequirement(package=str(k), version_spec=str(v))
        for k, v in value.items()
    )


def parse_manifest(data: Mapping[str, Any], root: Path) -> BundleManifest:
    """Baut ein :class:`BundleManifest` aus einem geparsten Mapping."""

    if not isinstance(data, Mapping):
        raise BundleError("bundle.yaml: Top-Level muss ein Mapping sein")

    bundle_id = _validate_id(data.get("id"))
    version = data.get("version")
    if not isinstance(version, str):
        raise BundleError("bundle.yaml: 'version' fehlt oder ist kein String")

    return BundleManifest(
        id=bundle_id,
        version=version,
        label=str(data.get("label", bundle_id)),
        description=str(data.get("description", "")).strip(),
        author=str(data.get("author", "")),
        homepage=str(data.get("homepage", "")),
        license=str(data.get("license", "")),
        requires=_parse_requires(data.get("requires")),
        facets=_as_tuple(data.get("facets"), "facets"),
        codebooks=_as_tuple(data.get("codebooks"), "codebooks"),
        methods=_as_tuple(data.get("methods"), "methods"),
        layouts=_as_tuple(data.get("layouts"), "layouts"),
        root=Path(root).resolve(),
    )


def load_manifest(bundle_root: Path) -> BundleManifest:
    """Laedt ``<bundle_root>/bundle.yaml``.

    Args:
        bundle_root: Verzeichnis, das eine ``bundle.yaml`` enthaelt.

    Returns:
        Das geparste :class:`BundleManifest`.

    Raises:
        BundleError: wenn die Datei fehlt oder das Schema verletzt ist.
    """

    bundle_root = Path(bundle_root)
    manifest_path = bundle_root / "bundle.yaml"
    if not manifest_path.is_file():
        raise BundleError(f"bundle.yaml nicht gefunden unter {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_manifest(data or {}, bundle_root)


__all__ = [
    "BundleError",
    "BundleRequirement",
    "BundleManifest",
    "InstalledBundle",
    "parse_manifest",
    "load_manifest",
]
