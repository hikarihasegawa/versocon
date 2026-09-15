# VersoCon — Regole di progetto

Valide in aggiunta alle regole globali (`~/.config/opencode/AGENTS.md`). Per questo repository valgono come autorizzazione permanente ai commit (il push resta separato).

## Commit (regola hard)
- Dopo ogni cambiamento validato: **commit atomici**, uno per unità logica di lavoro, solo file modificati in quel turno.
- Prima di committare: `pytest tests -q` verde nel turno corrente (e `node --check static/app.js` se il JS è stato toccato). Riportare il risultato reale.
- Lavoro in sospeso con più unità logiche → commit separati con staging selettivo, mai un commit unico.
- Messaggi: **inglese, Conventional Commits**, sintetici e chiari (una riga: cosa e perché; corpo solo se serve).
- Mai committare: segreti/credenziali, artefatti di test (es. `.playwright-mcp/`), output di build, file temporanei.
- **Push: solo su richiesta esplicita.**
