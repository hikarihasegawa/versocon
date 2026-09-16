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

## Release gate (regola hard)
Nessun artefatto (installer, MSIX, release Store) è pubblicabile finché questa checklist non è stata eseguita **sull'artefatto finale** (stesso SHA-256 che verrà pubblicato) e riportata con esito nel state file. Qualunque modifica dopo il gate → gate rieseguito per intero.

1. **Ambiente pulito**: installazione da zero su VM/Windows Sandbox o profilo nuovo — senza Python, senza Tesseract/ffmpeg nel `PATH`, utente senza privilegi admin.
2. **Scenari reali**: percorsi con spazi e caratteri non-ASCII; locale diversa dall'italiano; 2 monitor con DPI diversi; primo avvio (onboarding, 8 lingue, 2 temi).
3. **Tutti i flussi**: foto/EXIF, PDF editor con anteprima live, pulizia scansioni, OCR (ita+eng), video/audio/GIF, compressione — avviati **dall'app installata**, con verifica dell'effetto (file prodotto aperto/letto).
4. **Upgrade**: installazione sopra la versione Store precedente senza perdite; disinstallazione pulita; `GET /api/config` e footer mostrano la versione attesa.
5. **Listing Store**: descrizione IT/EN, screenshot, keywords e features riletti parola per parola **prima** della submission; nessun riferimento a versioni superate.
6. **Igiene**: 0 errori console nei flussi; nessun `crash.log` nuovo; hash dell'artefatto scaricato == hash dichiarato.
