# qualdatan-plugins

Plugin-Manager für [Qualdatan](https://github.com/GeneralPawz/Qualdatan): findet, installiert und verifiziert **Bundles** (YAML-Daten-Pakete mit Facets/Codebooks/Methoden/Layouts). Tap-Style — Bundles leben in GitHub-Repos der Publisher, ein späterer [Plugin-Server](https://github.com/Qualdatan/plugin-server) listet sie auf.

**Status**: Scaffold. Phase C füllt `manager`, `registry`, `loader`, `verify`, `cache`, `server_client`, `bundle` mit Leben.

## Install

```bash
pip install qualdatan-plugins
```

## Weiter

- [Architecture](architecture.md) — Tap-Modell, Verantwortlichkeiten der Subpakete.
- [API Reference](api.md) — wird aus Docstrings erzeugt (noch leer, Modul-Phase C).
- [Changelog](changelog.md).

## Lizenz

AGPL-3.0-only — siehe [LICENSE](https://github.com/Qualdatan/plugins/blob/main/LICENSE).
