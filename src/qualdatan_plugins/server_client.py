# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP-Client fuer den Qualdatan-Plugin-Server (Tap-Style-Index).

Der Plugin-Server ist ein schlanker Index-Dienst im Homebrew-Tap-Stil: er
listet Bundles (Taps), deren Git-Repo-URL, Versionen und Metadaten. Die
eigentlichen Bundle-Inhalte liegen in Git-Repos, *nicht* auf dem Server.

Dieses Modul definiert den **Client-Vertrag**; die Server-Implementierung
folgt spaeter. Endpunkte:

- ``GET  /index/search?q=<query>&limit=<n>``
- ``GET  /index/taps/<namespace>/<name>``
- ``POST /taps`` (OAuth-Bearer-Token erforderlich)
- ``GET  /healthz``

Example:
    >>> with PluginServerClient() as c:
    ...     hits = c.search("bim")
    ...     entry, versions = c.get_tap("qualdatan", "bim-basic")

Contract-Ambiguitaeten (spaeter serverseitig zu bestaetigen):
    * ``register_tap`` erwartet nur ``namespace`` + ``repo_url``; der Server
      leitet ``name`` aus ``bundle.yaml`` des Repos ab. Wir senden
      trotzdem beide explizit als JSON-Body.
    * Zeitstempel (``published_at``) wird als opaquer ISO-8601-String
      durchgereicht, kein ``datetime`` — Parsing ist Sache des Aufrufers.
    * Fehler-Payloads des Servers sind noch nicht spezifiziert; der Client
      nutzt als Message den Response-Text (max. 500 Zeichen).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TapEntry:
    """Ein Eintrag im Plugin-Server-Index.

    Attributes:
        namespace: Besitzer des Taps (z.B. GitHub-Org oder -User).
        name: Bundle-Name innerhalb des Namespaces.
        repo_url: Git-URL, unter der das Bundle lebt.
        latest_version: Zuletzt veroeffentlichte Version (SemVer, ohne ``v``).
        label: Menschenlesbarer Titel.
        description: Kurze Beschreibung.
        keywords: Such-Keywords.
        license: SPDX-Identifier.
    """

    namespace: str
    name: str
    repo_url: str
    latest_version: str
    label: str
    description: str
    keywords: tuple[str, ...]
    license: str

    @property
    def id(self) -> str:
        """Volle Bundle-Id im Format ``namespace/name``."""
        return f"{self.namespace}/{self.name}"


@dataclass(frozen=True)
class TapVersion:
    """Eine fuer einen Tap gelistete Version.

    Attributes:
        version: SemVer-String, z.B. ``"0.3.0"``.
        tag: Git-Tag, typischerweise ``"v" + version``.
        commit_sha: Commit-SHA des Tags.
        published_at: ISO-8601-Zeitstempel.
    """

    version: str
    tag: str
    commit_sha: str
    published_at: str


class PluginServerError(RuntimeError):
    """Wird bei Nicht-2xx-Antworten oder malformierten Payloads geworfen."""


# --- Parsing helpers ---------------------------------------------------------


def _parse_entry(data: Any) -> TapEntry:
    """Parse ein dict zu :class:`TapEntry`.

    Raises:
        PluginServerError: Bei fehlenden Pflichtfeldern.
    """
    if not isinstance(data, dict):
        raise PluginServerError(f"expected dict for TapEntry, got {type(data).__name__}")
    try:
        return TapEntry(
            namespace=str(data["namespace"]),
            name=str(data["name"]),
            repo_url=str(data["repo_url"]),
            latest_version=str(data.get("latest_version", "")),
            label=str(data.get("label", "")),
            description=str(data.get("description", "")),
            keywords=tuple(str(k) for k in data.get("keywords", ())),
            license=str(data.get("license", "")),
        )
    except KeyError as e:
        raise PluginServerError(f"missing required field in TapEntry: {e}") from e


def _parse_version(data: Any) -> TapVersion:
    """Parse ein dict zu :class:`TapVersion`."""
    if not isinstance(data, dict):
        raise PluginServerError(f"expected dict for TapVersion, got {type(data).__name__}")
    try:
        return TapVersion(
            version=str(data["version"]),
            tag=str(data.get("tag", f"v{data['version']}")),
            commit_sha=str(data["commit_sha"]),
            published_at=str(data.get("published_at", "")),
        )
    except KeyError as e:
        raise PluginServerError(f"missing required field in TapVersion: {e}") from e


# --- Client ------------------------------------------------------------------


class PluginServerClient:
    """HTTP-Client fuer den Qualdatan-Plugin-Server-Index.

    Standard-URL ist ein Platzhalter und kann ueberschrieben werden via
    Konstruktor-Argument oder Umgebungsvariable ``QUALDATAN_PLUGIN_SERVER``.

    Der Client ist stateless; Authentifizierung erfolgt per Bearer-Token
    (OAuth, vom Login-Flow ausserhalb dieses Moduls erzeugt).

    Args:
        base_url: Basis-URL des Servers. Prioritaet:
            ctor-Arg > ``QUALDATAN_PLUGIN_SERVER`` > :attr:`DEFAULT_URL`.
        token: Optionaler Bearer-Token fuer geschuetzte Endpunkte.
        timeout: HTTP-Timeout in Sekunden.
        client: Optionaler vorkonfigurierter ``httpx.Client``. Wird dieser
            uebergeben, wird er in :meth:`close` *nicht* geschlossen.
    """

    DEFAULT_URL = "https://plugins.qualdatan.dev"  # placeholder

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        resolved = base_url or os.environ.get("QUALDATAN_PLUGIN_SERVER") or self.DEFAULT_URL
        self._base_url = resolved.rstrip("/")
        self._token = token
        self._timeout = timeout
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(timeout=timeout)
            self._owns_client = True

    # -- context mgmt --------------------------------------------------------

    def __enter__(self) -> PluginServerClient:
        return self

    def __exit__(self, *a: object) -> None:
        self.close()

    def close(self) -> None:
        """Schliesse den internen ``httpx.Client`` (nur wenn selbst erzeugt)."""
        if self._owns_client:
            self._client.close()

    # -- internal ------------------------------------------------------------

    def _headers(self, *, auth: bool = False) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        auth: bool = False,
    ) -> Any:
        try:
            resp = self._client.request(
                method,
                self._url(path),
                params=params,
                json=json_body,
                headers=self._headers(auth=auth),
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise PluginServerError(f"HTTP error for {method} {path}: {e}") from e

        if resp.status_code >= 400:
            text = resp.text[:500]
            raise PluginServerError(
                f"{method} {path} failed: {resp.status_code} {resp.reason_phrase} — {text}"
            )
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise PluginServerError(f"malformed JSON from {method} {path}: {e}") from e

    # -- public API ----------------------------------------------------------

    def search(self, query: str = "", *, limit: int = 25) -> list[TapEntry]:
        """Suche Taps per Freitext.

        Args:
            query: Suchbegriff (leer = alle).
            limit: Maximale Ergebnismenge.

        Returns:
            Liste der Treffer-Eintraege.
        """
        payload = self._request("GET", "/index/search", params={"q": query, "limit": limit})
        if not isinstance(payload, dict) or "results" not in payload:
            raise PluginServerError("search: expected {'results': [...]} payload")
        results = payload["results"]
        if not isinstance(results, list):
            raise PluginServerError("search: 'results' is not a list")
        return [_parse_entry(r) for r in results]

    def get_tap(self, namespace: str, name: str) -> tuple[TapEntry, list[TapVersion]]:
        """Hole Metadaten und Versionsliste eines Taps.

        Args:
            namespace: Besitzer.
            name: Bundle-Name.

        Returns:
            Tuple aus :class:`TapEntry` und Liste von :class:`TapVersion`.
        """
        payload = self._request("GET", f"/index/taps/{namespace}/{name}")
        if not isinstance(payload, dict) or "entry" not in payload:
            raise PluginServerError("get_tap: expected {'entry': ..., 'versions': [...]} payload")
        entry = _parse_entry(payload["entry"])
        versions_raw = payload.get("versions", [])
        if not isinstance(versions_raw, list):
            raise PluginServerError("get_tap: 'versions' is not a list")
        versions = [_parse_version(v) for v in versions_raw]
        return entry, versions

    def register_tap(self, namespace: str, repo_url: str) -> TapEntry:
        """Registriere einen neuen Tap (benoetigt Bearer-Token).

        Der Server verifiziert Besitz des ``namespace`` via OAuth und liest
        ``bundle.yaml`` aus ``repo_url`` zur Ableitung von ``name`` und
        Metadaten.

        Args:
            namespace: Besitzer (muss zum OAuth-Account passen).
            repo_url: Git-URL des Bundle-Repos.

        Returns:
            Der neu registrierte Eintrag.

        Raises:
            PluginServerError: Bei fehlendem Token oder Server-Fehler.
        """
        if not self._token:
            raise PluginServerError("register_tap requires a bearer token")
        payload = self._request(
            "POST",
            "/taps",
            json_body={"namespace": namespace, "repo_url": repo_url},
            auth=True,
        )
        if not isinstance(payload, dict) or "entry" not in payload:
            raise PluginServerError("register_tap: expected {'entry': ...} payload")
        return _parse_entry(payload["entry"])

    def healthz(self) -> dict:
        """Liveness-Check. Gibt das rohe JSON-Dict zurueck."""
        payload = self._request("GET", "/healthz")
        if not isinstance(payload, dict):
            raise PluginServerError("healthz: expected object payload")
        return payload
