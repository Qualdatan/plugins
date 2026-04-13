# qualdatan-plugins

Plugin-Manager fuer [Qualdatan](https://github.com/GeneralPawz/Qualdatan):
findet, installiert und verifiziert **Bundles** (YAML-Daten-Pakete mit
Facets/Codebooks/Methoden/Layouts). Tap-Style — Bundles leben in GitHub-
Repos der Publisher, ein spaeterer [Plugin-Server](https://github.com/Qualdatan/plugin-server)
listet sie auf.

**Status**: Scaffold. Phase C fuellt `manager`, `registry`, `loader`,
`verify`, `cache`, `server_client`, `bundle` mit Leben.

## Dokumentation

- Live-Site: https://qualdatan.github.io/plugins/
- Lokaler Preview: `pip install -e ".[docs]" && mkdocs serve`
- Docs-Policy und -Struktur: [CLAUDE.md](CLAUDE.md)

## Lizenz

AGPL-3.0-only — siehe [LICENSE](LICENSE).
