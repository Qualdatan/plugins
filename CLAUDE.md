# CLAUDE.md — qualdatan-plugins

## Docs-Policy

Docs sind **nicht optional** und werden **mit dem Code** gepflegt. Die Site wird automatisch per GitHub Pages unter `https://qualdatan.github.io/plugins/` veröffentlicht.

### Primäre API-Doku = Docstrings im Code

- Jede Änderung an öffentlicher API → Docstring mitpflegen.
- **Stil**: Google-Docstring (`Args:`, `Returns:`, `Raises:`, `Example:`). Section-Marker englisch, Prosa darf deutsch sein.
- Keine Redundanz: Docstring-Inhalt wird **nicht** in `docs/*.md` wiederholt.

### Narrative Docs unter `docs/`

- `docs/index.md` — Purpose, Install, Quickstart.
- `docs/architecture.md` — Tap-Style-Modell, Manager/Registry/Loader/Verify/Cache-Rollen, Bundle-Format.
- `docs/api.md` — nur mkdocstrings-Direktiven (`::: qualdatan_plugins.<modul>`).
- `docs/changelog.md` — Keep-a-Changelog.
- Neue Konzepte → neue MD-Datei + Eintrag in `mkdocs.yml` unter `nav`.

### Lokaler Preview

```bash
pip install -e ".[docs]"
mkdocs serve
```

### Deploy

Automatisch via `.github/workflows/docs.yml` bei Push auf `main`. Pages-Quelle einmalig auf Branch `gh-pages` setzen.
