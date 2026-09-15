# VersoCon — Regole di progetto

Valide in aggiunta alle regole globali (`~/.config/opencode/AGENTS.md`). Per questo repository valgono come autorizzazione permanente ai commit (il push resta separato).

## Commit (regola hard)
- Dopo ogni cambiamento validato: **commit atomici**, uno per unità logica di lavoro, solo file modificati in quel turno.
- Prima di committare: `pytest tests -q` verde nel turno corrente (e `node --check static/app.js` se il JS è stato toccato). Riportare il risultato reale.
- Lavoro in sospeso con più unità logiche → commit separati con staging selettivo, mai un commit unico.
- Messaggi: **inglese, Conventional Commits**, sintetici e chiari (una riga: cosa e perché; corpo solo se serve).
- Mai committare: segreti/credenziali, artefatti di test (es. `.playwright-mcp/`), output di build, file temporanei.
- **Push: solo su richiesta esplicita.**

## Allineamento GitHub (regola hard)
- A ogni push/release, docs GitHub, `.github/workflows/`, GitHub Release, manifesti winget/scoop e checksum devono essere **professionalmente allineati** a versione reale e modifiche incluse: mai riferimenti a versioni superate, asset inesistenti o hash non verificati.
- Rilascio: bump `app/version.py` (unica fonte; i workflow riscrivono ISS/MSIX dal tag), poi README + `docs/security.md` (SHA-256 dell'asset pubblicato), `packaging/winget/*` e `packaging/scoop/versocon.json` (version/url/hash), release notes professionali.
- Ogni allineamento va verificato con comandi reali (asset scaricato → SHA-256, `gh release view`, contenuto servito da raw.githubusercontent) e l'esito riportato.
- README e docs pubbliche descrivono **l'ultima versione rilasciata**: le modifiche già su master ma non ancora rilasciate non vanno annunciate come disponibili finché non escono con un rilascio (bump + note).
