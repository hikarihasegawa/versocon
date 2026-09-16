# VersoCon — v0.3.0 — Release notes

## ✨ What's new
- ✍️ **Complete PDF editor** — 17 tools: rotate, delete/reorder/insert/extract pages, watermark, text and stamps, sticky notes, highlight/underline, freehand ink, redaction, find & replace, Bates numbering, header/footer, fill PDF forms, sign (5 handwriting fonts or draw your own), password protect/unprotect and searchable OCR. **Every change is now previewed live** before you apply it, and edits chain: each result becomes the working document.
- 🎨 **New look, two themes** — a dashboard-style **Pro** theme (default) and the original anime **Manga** theme, switchable in the header; a first-run welcome dialog lets you pick language, theme and (optionally) update checks.
- 🔎 **Scan cleanup** — straighten tilted scans, remove shadows, adaptive black & white and 4-corner perspective crop, for both photos and scanned PDFs (OpenCV engine bundled).
- 🛡️ **Privacy controls** — one-click removal of EXIF/GPS metadata from photos. Everything still runs 100% offline.
- 🎬 **More video tools** — extract audio (MP3/M4A) and turn videos into animated GIFs; long jobs now show a real progress bar with a cancel button.
- 🌍 **8 languages** — Italian, English, Spanish, French, German, Portuguese, Chinese, Japanese.
- ♿ **Accessibility** — measured WCAG contrast, visible keyboard focus and reduced-motion support across both themes.
- 🔧 **Better engine detection** — ffmpeg and Tesseract are found automatically in WinGet, Chocolatey, Scoop and standard install locations; a "Recheck" button picks up installs made while the app is open.
- 🧪 **Quality** — the whole suite plus a real-browser end-to-end smoke test now run on every change.
- Plus dozens of fixes: PDF text replacement preserves background and rotated text, protected PDFs open correctly in the editor, editor layout and translations cleaned up.

## 🔒 Is it safe? / È sicuro?

**Yes — VersoCon is 100% local, open-source, with no telemetry and no account.**
It runs entirely on your machine (`127.0.0.1`); nothing ever goes online.

> ### Windows shows "Windows protected your PC" (SmartScreen)
> This is **normal** for unsigned open-source software and does **not** mean VersoCon contains a virus.
> Before you proceed, verify:
>
> 1. **SHA-256** — compare the hash of your downloaded file with the one on this release page
>    (Windows: `Get-FileHash versocon-setup-*.exe -Algorithm SHA256`).
> 2. **VirusTotal** (optional) — upload your copy at
>    [virustotal.com](https://www.virustotal.com/gui/home/url) and check the result.
> 3. **Source code** — the code that built this file is on
>    [github.com/hikarihasegawa/versocon](https://github.com/hikarihasegawa/versocon).
>
> If everything checks out, click **More info → Run anyway / Esegui comunque**.
>
> ### Prefer an installer that never asks?
> Install through a package manager:
> ```
> winget install HikariHasegawa.VersoCon    # official Windows package manager (submission under review)
> scoop bucket add HikariHasegawa https://github.com/HikariHasegawa/bucket
> scoop install versocon                     # Scoop, from the author's bucket above (live now)
> ```

<!-- Italiano -->

**Sì — VersoCon è 100% locale, open-source, senza telemetria e senza account.**
Ogni cosa gira sulla tua macchina (`127.0.0.1`); nessun file va mai online.

> ### Windows mostra "Windows ha protetto il tuo PC" (SmartScreen)
> È **normale** per software open-source non firmato e **non** indica la presenza di un virus.
> Prima di procedere, verifica:
>
> 1. **SHA-256** — confronta l'hash del file scaricato con quello della pagina della release
>    (Windows: `Get-FileHash versocon-setup-*.exe -Algorithm SHA256`).
> 2. **VirusTotal** (facoltativo) — carica la tua copia su
>    [virustotal.com](https://www.virustotal.com/gui/home/url) e controlla il risultato.
> 3. **Codice sorgente** — chi ha costruito questo file è su
>    [github.com/hikarihasegawa/versocon](https://github.com/hikarihasegawa/versocon).
>
> Se tutto è OK → **Altre informazioni → Esegui comunque**.
>
> ### Preferisci un canale che non chiede nulla?
> Installa con un package manager:
> ```
> winget install HikariHasegawa.VersoCon    # canale Microsoft (PR in attesa)
> scoop bucket add HikariHasegawa https://github.com/HikariHasegawa/bucket
> scoop install versocon                     # Scoop, dal bucket dell'autore qui sopra (già attivo)
> ```

## FAQ

**Q: Why does Windows warn me?** / **Perché Windows mi avvisa?**
A: The installer is not digitally signed (a code-signing certificate requires a business entity — see roadmap). SmartScreen is a generic caution, not a malware report. / Non è firmato con certificato (serve una ditta — vedi roadmap). SmartScreen è una cautela generica, non un report di malware.

**Q: How do I know it's not a virus?** / **Come so che non è un virus?**
A: (1) The source is public on GitHub. (2) The binary you run is built *from* that source in a public GitHub Actions log. (3) SHA-256 and VirusTotal give you 2 independent confirmations. / (1) Il codice è pubblico. (2) Il binario che esegui è costruito *da* quello in una CI GHA pubblica. (3) SHA-256 e VirusTotal danno 2 verifiche indipendenti.

**Q: When will the warning go away?** / **Quando sparisce l'avviso?**
A: For most users within weeks, once SmartScreen has enough "clean install" reports. Definitively, once we get a code-signing certificate (needs a business license). / Per la maggior parte degli utenti in poche settimane. In modo definitivo quando avremo il certificato di firma (richiede una ditta).

**Q: Does v0.3.0 include the security fixes from v0.2.5/v0.2.6?** / **La v0.3.0 include i fix di sicurezza di v0.2.5/v0.2.6?**
A: Yes — all of them (path traversal, DNS-rebinding/CSRF protection, hidden console windows, Italian translation fixes). / Sì — tutti (path traversal, protezione DNS-rebinding/CSRF, finestre console nascoste, fix delle traduzioni italiane).
