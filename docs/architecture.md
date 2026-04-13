# Architecture

`qualdatan-plugins` ist ein **Tap-Style-Plugin-Manager**: Bundles (YAML-Daten-Pakete) liegen in GitHub-Repos der Publisher. Der Plugin-Manager selbst kennt keine Domäne, sondern nur das Bundle-Format.

## Rolle der Subpakete (Phase C)

| Modul | Verantwortlich für |
|-------|--------------------|
| `manager` | High-level Einstieg: install, update, remove |
| `registry` | Lokaler Index installierter Bundles |
| `loader` | YAML → Facet-Instanzen (via `qualdatan_core.facets.loader`) |
| `verify` | Signatur-/Hash-Prüfung |
| `cache` | Download-Cache (via `platformdirs`) |
| `server_client` | HTTP-Client zum Plugin-Server (Listing/Suche) |
| `bundle` | Bundle-Schema und Serialisierung |

## Abgrenzung

- **Facet-Typen** (Klassen) kommen aus `qualdatan-core` bzw. aus Entry-Point-Plugins — **nicht** aus diesem Repo.
- **Bundles** liefern nur Konfigurationen/Daten, keine Python-Klassen.
- **Plugin-Server** ist ein separates Projekt und liefert nur Listings.

## Lizenz & SPDX

AGPL-3.0-only. Neue Quelldateien beginnen mit:

```python
# SPDX-License-Identifier: AGPL-3.0-only
```
