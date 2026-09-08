# VersoCon — setup (Windows, PowerShell)
# Installa le dipendenze Python + (opzionale) Tesseract per OCR.
# Esecuzione:  powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Continue"

function Say([string]$m) { Write-Host $m -ForegroundColor Cyan }

# 1) Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Warning "Python non trovato: installalo da winget install Python.Python.3.11"
}

# 2) Dipendenze base
Say "=== Python: dipendenze base ==="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "Fail install dip. base — stop"; exit 1 }

# 3) OCR (opzionale) — cerca Tesseract nel PATH O nei path di installazione noti
function Find-Tesseract {
    if (Get-Command tesseract -ErrorAction SilentlyContinue) { return $true }
    if (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") { return $true }
    if (Test-Path "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe") { return $true }
    if (Test-Path (Join-Path $env:LOCALAPPDATA "Programs\Tesseract-OCR\tesseract.exe")) { return $true }
    return $false
}
if (Find-Tesseract) {
    Say "Tesseract presente (PATH o path di installazione rilevato)."
} else {
    Say "=== Tesseract (OCR, opzionale) ==="
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Tento winget install Tesseract-OCR ..."
        winget install --id tesseract-ocr.tesseract -e --accept-source-agreements --accept-package-agreements
        # aggiorna PATH della session
        $t = "C:\Program Files\Tesseract-OCR\tesseract.exe"
        if (Test-Path $t) {
            $env:Path += ";C:\Program Files\Tesseract-OCR"
            Say "Tesseract installato (aggiorna PATH sessione)."
        } else {
            Write-Warning "winget non ha trovato Tesseract. Installalo a mano o salta OCR."
        }
    } else {
        Write-Warning "winget non disponibile. Per OCR: winget install Tesseract-OCR oppure salta."
    }
}

# 4) pytesseract — SI installa SEMPRE (pacchetto Python puro, piccolo):
#    così anche Tesseract installato dopo (o fuori PATH, es. C:\Program Files
#    \Tesseract-OCR) è rilevato via path noti e OCR funziona senza ri-installare.
Say "=== Python: OCR (pytesseract) ==="
python -m pip install -r requirements-ocr.txt
if (Get-Command tesseract -ErrorAction SilentlyContinue -or `
    (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") -or `
    (Test-Path "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")) {
    Say "Tesseract rilevato: OCR disponibile."
} else {
    Say "OCR: Tesseract non ancora rilevato. App funzionante; poi installalo con:`n   winget install --id tesseract-ocr.tesseract -e"
}

Say "=== Fatto ==="
Say "Avvia:  python -m uvicorn app.main:app --host 127.0.0.1 --port 8321"
Say "Poi apri: http://127.0.0.1:8321"
