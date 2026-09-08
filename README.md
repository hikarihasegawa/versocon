# VersoCon 変

> **Converti foto, PDF e video — al 100% sul tuo computer.** Niente cloud, niente account, niente upload: i tuoi file non lasciano mai il tuo PC.

[![License: MIT](https://img.shields.io/badge/License-MIT-4dabf7?logo=mit&logoColor=white)](LICENSE.md)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](requirements.txt)
[![Windows](https://img.shields.io/badge/Windows-Setup-0078d6?logo=windows&logoColor=white)](#)
[![Linux](https://img.shields.io/badge/Linux-Deb-__AppImage-2b8a3e?logo=linux&logoColor=white)](#)
[![Supporta il progetto](https://img.shields.io/badge/Ko--fi-Supporta-ff5f5f?logo=ko-fi&logoColor=white)](https://ko-fi.com/hikari22)

<p align="center">
  <img src="assets/demo/versocon-demo.gif" alt="Demo di VersoCon: conversione HEIC, editor PDF con firma e compressione PDF" width="640">
</p>

VersoCon è un convertitore di file con interfaccia desktop in stile **manga anime**. Converte foto HEIC, trasforma PDF in immagini (e viceversa), firma e organizza PDF, estrae testo, comprime e rinomina — **tutto in locale**.

## ⚡ Perché VersoCon

- 🔒 **Privacy totale**: elaborazione esclusivamente su `127.0.0.1`, nessun dato inviato online.
- 📸 **HEIC nativo**: le foto iPhone (`.heic`) si aprono e si convertono senza app di terze parti.
- 📄 **Kit PDF completo**: editor con anteprima live, firma (disegnata o da nome), riordino, rotazione, watermark, merge e split.
- 🎬 **Video**: transcode MP4/WebM (se hai `ffmpeg`).
- 🪶 **Leggero e offline**: un solo eseguibile, nessuna dipendenza da servizi web.
- 🎨 **Interfaccia curata**: tema Shonen Manga, drag & drop, toast, animazioni.

## ✨ Funzionalità

| Area | Cosa fa |
|------|---------|
| **Foto** | HEIC / HEIF / JPG / PNG / WebP / BMP / TIFF / GIF → JPEG, PNG o WebP. Qualità, ridimensionamento (lato max), EXIF/rotazione preservati, GIF animate mantenute, batch fino a 500 file, download singolo o ZIP. |
| **PDF** | PDF → immagini · immagini → PDF · merge · split · rinomina batch. |
| **Editor PDF** | Anteprima live in-browser, firma disegnata o generata da nome (4 stili calligrafici), firma da immagine, posizionamento/ridimensionamento libero, rotazione e opacità, watermark, riordino/rotazione/cancellazione pagine, testo. |
| **Comprimi** | Riduci dimensione di immagini (obiettivo in byte o qualità) e PDF (basso/medio/alto), con indicazione del risparmio. |
| **PDF → testo** | Estrazione testo e OCR (Tesseract, opzionale). |
| **Video** | Transcode in MP4 o WebM (richiede `ffmpeg`). |

## 🚀 Installazione

### Da store / installer (consigliato)
- **Windows**: scarica `versocon-setup-X.Y.Z.exe` dalle [Releases](https://github.com/hikarihasegawa/versocon/releases) e avvialo. Oppure, quando disponibile, `winget install VersoCon` / `scoop install versocon`.
- **Linux**: `.deb` per apt o `AppImage` portatile dalle [Releases](https://github.com/hikarihasegawa/versocon/releases).

> Ogni piattaforma: installazione locale, nessun account richiesto.

### Da codice sorgente

```bash
git clone https://github.com/hikarihasegawa/versocon.git
cd versocon
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# OCR opzionale (Tesseract nel sistema + pytesseract)
pip install -r requirements-ocr.txt
```

Oppure usa gli script di setup che installano anche Tesseract:

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

```bash
# Linux / macOS
bash install.sh
```

### Avvio

```bash
python run.py              # finestra desktop (pywebview) o browser se non disponibile
python run.py --browser    # forza il browser di default
# oppure, senza pywebview:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8321
# poi apri: http://127.0.0.1:8321
```

## 📋 Requisiti

- **Python 3.11+** per l'esecuzione da sorgente.
- **Dipendenze di base**: `fastapi`, `uvicorn`, `pillow`, `pillow-heif`, `pymupdf`, `pywebview` (vedi `requirements.txt`).
- **Opzionale**:
  - `ffmpeg` nel PATH per la conversione video.
  - `Tesseract` per l'OCR (opzionale).

## 🗂️ Struttura del progetto

```
versocon/
├─ app/            # FastAPI: endpoint API + costanti
├─ converters/     # logica di conversione (immagini, documenti, video, PDF, firma, compressione)
├─ static/         # frontend HTML+CSS+JS (no build step) + vendor (pdf.js)
├─ assets/         # font, logo, demo
├─ packaging/      # PyInstaller spec, icone, Inno Setup, make_icon
├─ tests/          # suite pytest
├─ run.py          # lanciatore desktop/browser
├─ requirements.txt
└─ PROGRESS.md     # stato e roadmap dello sviluppo (fonte di verità)
```

## 🧪 Test

```bash
.venv\Scripts\python -m pytest tests -q   # Windows
# o:
python -m pytest tests -q
```

## 🤝 Contribuire e supporto

Apri un issue o un pull request. Se ti è utile, puoi
[sostenere lo sviluppo ☕](https://ko-fi.com/hikari22).

## 📄 Licenza

[MIT](LICENSE.md) — libera da usare, modificare e ridistribuire.
