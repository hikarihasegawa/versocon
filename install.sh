#!/usr/bin/env bash
# VersoCon — setup (Linux / macOS). Installa dipendenze Python + (opzionale) Tesseract OCR.
# Esecuzione: bash install.sh
set -euo pipefail

say() { printf '\n\033[36m%s\033[0m\n' "$1"; }

# 1) Python
if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "Python non trovato: installalo." >&2; exit 1
fi
PY=$(command -v python || command -v python3)

# 2) Dipendenze base
say "=== Python: dipendenze base ==="
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# 3) Tesseract (OCR, opzionale)
install_tesseract() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-ita
  elif command -v brew >/dev/null 2>&1; then
    brew install tesseract tesseract-lang
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y tesseract tesseract-langpack-ita
  else
    echo "Pacchetto manager non riconosciuto: installa tesseract a mano." >&2; return 1
  fi
}

if command -v tesseract >/dev/null 2>&1; then
  say "Tesseract già presente."
else
  say "=== Tesseract (OCR, opzionale) ==="
  if install_tesseract || command -v tesseract >/dev/null 2>&1; then
    :
  else
    echo "OCR saltato (Tesseract assente). App funzionante senza OCR."
    exit 0
  fi
fi

# 4) pytesseract
say "=== Python: OCR (pytesseract) ==="
"$PY" -m pip install -r requirements-ocr.txt

say "=== Fatto ==="
echo "Avvia:  $PY -m uvicorn app.main:app --host 127.0.0.1 --port 8321"
echo "Poi apri: http://127.0.0.1:8321"
