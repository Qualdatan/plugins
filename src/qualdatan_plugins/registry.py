# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite-Registry fuer installierte Bundles + per-Projekt-Aktivierung.

Die Registry speichert **Metadaten** ueber installierte Bundles (Herkunft,
Commit-SHA, Install-Pfad) und welche Bundle-Version in welchem Projekt
aktiv ist. Der tatsaechliche Manifest-Inhalt wird bei jedem Read-Aufruf
frisch aus ``<install_path>/bundle.yaml`` geparst (single source of truth).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir

from .bundle import BundleError, InstalledBundle, load_manifest


_ENV_DB = "QUALDATAN_PLUGIN_REGISTRY"
_SCHEMA_VERSION = 1


def _default_db_path() -> Path:
    env = os.environ.get(_ENV_DB)
    if env:
        return Path(env)
    return Path(user_data_dir("Qualdatan", "Qualdatan")) / "plugins.db"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS installed (
    bundle_id TEXT NOT NULL,
    version TEXT NOT NULL,
    install_path TEXT NOT NULL,
    source TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    installed_at TEXT NOT NULL,
    PRIMARY KEY (bundle_id, version)
);
CREATE TABLE IF NOT EXISTS active (
    project_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    version TEXT NOT NULL,
    PRIMARY KEY (project_id, bundle_id),
    FOREIGN KEY (bundle_id, version) REFERENCES installed(bundle_id, version)
);
"""


class PluginRegistry:
    """SQLite-Index ueber alle installierten Bundles.

    Persistenz:
        Der DB-Pfad kommt aus ``QUALDATAN_PLUGIN_REGISTRY`` oder default
        ``<platformdirs appdata>/plugins.db``. Bei Fehlen wird Schema
        automatisch angelegt.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        """Pfad zur SQLite-Datei."""
        return self._db_path

    def _ensure_schema(self) -> None:
        cur = self._conn.execute("PRAGMA user_version")
        (version,) = cur.fetchone()
        if version == 0:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._conn.commit()
        elif version != _SCHEMA_VERSION:
            raise BundleError(
                f"plugins.db hat schema-version {version}, erwartet {_SCHEMA_VERSION}"
            )

    # ------------------------------------------------------------------
    # Install-Tabelle
    # ------------------------------------------------------------------
    def record_install(self, ib: InstalledBundle) -> None:
        """Legt oder aktualisiert einen Eintrag in der ``installed``-Tabelle."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO installed
                (bundle_id, version, install_path, source, origin, commit_sha, installed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bundle_id, version) DO UPDATE SET
                install_path=excluded.install_path,
                source=excluded.source,
                origin=excluded.origin,
                commit_sha=excluded.commit_sha,
                installed_at=excluded.installed_at
            """,
            (
                ib.id,
                ib.version,
                str(ib.install_path),
                ib.source,
                ib.origin,
                ib.commit_sha,
                now,
            ),
        )
        self._conn.commit()

    def remove_install(self, bundle_id: str, version: str) -> None:
        """Loescht installed- und zugehoerige active-Eintraege."""
        self._conn.execute(
            "DELETE FROM active WHERE bundle_id=? AND version=?",
            (bundle_id, version),
        )
        self._conn.execute(
            "DELETE FROM installed WHERE bundle_id=? AND version=?",
            (bundle_id, version),
        )
        self._conn.commit()

    def _row_to_installed(self, row: tuple) -> InstalledBundle | None:
        bundle_id, version, install_path, source, origin, commit_sha, _ = row
        path = Path(install_path)
        try:
            manifest = load_manifest(path)
        except BundleError:
            return None
        return InstalledBundle(
            manifest=manifest,
            install_path=path,
            source=source,
            origin=origin,
            commit_sha=commit_sha,
        )

    def list_installed(self) -> list[InstalledBundle]:
        """Alle DB-Eintraege, Manifest re-parsed von Disk."""
        cur = self._conn.execute(
            "SELECT bundle_id, version, install_path, source, origin, commit_sha, installed_at "
            "FROM installed ORDER BY bundle_id, version"
        )
        out: list[InstalledBundle] = []
        for row in cur.fetchall():
            ib = self._row_to_installed(row)
            if ib is not None:
                out.append(ib)
        return out

    def get_installed(
        self,
        bundle_id: str,
        version: str | None = None,
    ) -> InstalledBundle | None:
        """Einen installierten Eintrag holen.

        Args:
            bundle_id: ``namespace/name``.
            version: exakter Semver; wenn ``None``, wird der (lexikographisch)
                neueste Eintrag geliefert.

        Returns:
            :class:`InstalledBundle` oder ``None``.
        """
        if version is None:
            cur = self._conn.execute(
                "SELECT bundle_id, version, install_path, source, origin, commit_sha, "
                "installed_at FROM installed WHERE bundle_id=? ORDER BY version DESC LIMIT 1",
                (bundle_id,),
            )
        else:
            cur = self._conn.execute(
                "SELECT bundle_id, version, install_path, source, origin, commit_sha, "
                "installed_at FROM installed WHERE bundle_id=? AND version=?",
                (bundle_id, version),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_installed(row)

    # ------------------------------------------------------------------
    # Aktivierung
    # ------------------------------------------------------------------
    def activate(
        self,
        bundle_id: str,
        version: str,
        project_id: str = "",
    ) -> None:
        """Markiert ``<bundle_id>@<version>`` als aktiv in ``project_id``.

        Leerer ``project_id`` bedeutet globaler Default.
        """
        cur = self._conn.execute(
            "SELECT 1 FROM installed WHERE bundle_id=? AND version=?",
            (bundle_id, version),
        )
        if cur.fetchone() is None:
            raise BundleError(
                f"cannot activate {bundle_id}@{version}: not in installed table"
            )
        self._conn.execute(
            """
            INSERT INTO active (project_id, bundle_id, version) VALUES (?, ?, ?)
            ON CONFLICT(project_id, bundle_id) DO UPDATE SET version=excluded.version
            """,
            (project_id, bundle_id, version),
        )
        self._conn.commit()

    def deactivate(self, bundle_id: str, project_id: str = "") -> None:
        """Entfernt einen aktiven Eintrag (no-op wenn nicht vorhanden)."""
        self._conn.execute(
            "DELETE FROM active WHERE project_id=? AND bundle_id=?",
            (project_id, bundle_id),
        )
        self._conn.commit()

    def list_active(self, project_id: str = "") -> list[InstalledBundle]:
        """Liste der aktiven Bundles in ``project_id``."""
        cur = self._conn.execute(
            """
            SELECT i.bundle_id, i.version, i.install_path, i.source, i.origin,
                   i.commit_sha, i.installed_at
            FROM active a
            JOIN installed i
              ON i.bundle_id = a.bundle_id AND i.version = a.version
            WHERE a.project_id = ?
            ORDER BY i.bundle_id
            """,
            (project_id,),
        )
        out: list[InstalledBundle] = []
        for row in cur.fetchall():
            ib = self._row_to_installed(row)
            if ib is not None:
                out.append(ib)
        return out

    # ------------------------------------------------------------------
    def close(self) -> None:
        """Schliesst die SQLite-Verbindung."""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


__all__ = ["PluginRegistry"]
