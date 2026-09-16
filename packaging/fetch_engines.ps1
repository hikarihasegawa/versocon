<#
.SYNOPSIS
Scarica e verifica i motori esterni da includere nel bundle di release.

.DESCRIPTION
Pin espliciti, verificati con SHA-256 prima dell'uso:
- Tesseract 5.5.3.20260724 (package Chocolatey omonimo: il checksum lo applica
  Chocolatey; qui si verifica poi versione e lingue dell'installazione) in
  %ProgramFiles%\Tesseract-OCR;
- modello italiano "best" di Tesseract (l'installer non lo include in modo
  deterministico), scaricato e verificato a parte;
- ffmpeg 8.1.2 "essentials" di Gyan (GPLv3), zip verificato con lo SHA-256
  dichiarato dal fornitore.

Con `-TesseractDir` si usa un'installazione esistente (verifica locale).
Se `GITHUB_ENV` esiste (GitHub Actions), esporta `VERSOCON_TESSERACT_DIR`,
`VERSOCON_FFMPEG_DIR` e `VERSOCON_REQUIRE_ENGINES=1` per lo spec PyInstaller.

.EXAMPLE
pwsh packaging/fetch_engines.ps1 -DestDir "$env:TEMP\engines"
#>
[CmdletBinding()]
param(
    [string]$DestDir = (Join-Path ([IO.Path]::GetTempPath()) "versocon-engines"),
    [string]$TesseractDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- pin (non aggiornare senza verificare download + SHA-256) -----------------
$TessVersion = "5.5.3.20260724"
$ItaUrl      = "https://raw.githubusercontent.com/tesseract-ocr/tessdata/ced78752cc61322fb554c280d13360b35b8684e4/ita.traineddata"
$ItaSha256   = "4F7476C611312BEB8F8E182888DA08EA642D9824AE4402CC6235F61AB1406406"
$FfmpegUrl   = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip"
$FfmpegSha256 = "DB580001CAA24AC104C8CB856CD113A87B0A443F7BDF47D8C12B1D740584A2EC"
$FfmpegFolder = "ffmpeg-8.1.2-essentials_build"

$CacheDir = Join-Path $DestDir "cache"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

function Get-PinnedFile {
    param([string]$Url, [string]$Sha256, [string]$FileName)

    $path = Join-Path $CacheDir $FileName
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "download: $Url"
        Invoke-WebRequest -Uri $Url -OutFile $path -UseBasicParsing
    }
    $got = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($got -ne $Sha256.ToUpperInvariant()) {
        throw "SHA-256 inatteso per $FileName`n  atteso:   $Sha256`n  ottenuto: $got"
    }
    Write-Host ("verificato: {0} ({1:N0} byte)" -f $FileName, (Get-Item -LiteralPath $path).Length)
    return $path
}

# --- Tesseract ----------------------------------------------------------------
if ($TesseractDir) {
    $tess = $TesseractDir
    Write-Host "Tesseract: uso l'installazione indicata ($tess)"
} else {
    $tess = Join-Path $env:ProgramFiles "Tesseract-OCR"
    $tessExe = Join-Path $tess "tesseract.exe"
    $current = if (Test-Path -LiteralPath $tessExe) { (& $tessExe --version | Select-Object -First 1) } else { "" }
    if ($current -notmatch [regex]::Escape($TessVersion)) {
        Write-Host "choco install tesseract --version=$TessVersion"
        & choco install tesseract --version=$TessVersion -y --no-progress --limit-output
        if ($LASTEXITCODE -ne 0) { throw "choco install tesseract fallito (exit $LASTEXITCODE)" }
    } else {
        Write-Host "Tesseract gia' presente: $current"
    }
}

$tessExe = Join-Path $tess "tesseract.exe"
if (-not (Test-Path -LiteralPath $tessExe)) { throw "tesseract.exe non trovato in $tess" }
$versionLine = (& $tessExe --version | Select-Object -First 1)
if ($versionLine -notmatch [regex]::Escape($TessVersion)) {
    throw "versione Tesseract inattesa: '$versionLine' (attesa $TessVersion)"
}

$ita = Get-PinnedFile -Url $ItaUrl -Sha256 $ItaSha256 -FileName "ita.traineddata"
$tessdata = Join-Path $tess "tessdata"
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null
Copy-Item -LiteralPath $ita -Destination (Join-Path $tessdata "ita.traineddata") -Force

$langs = @(& $tessExe --list-langs)
Write-Host "lingue Tesseract: $($langs -join ', ')"
foreach ($need in @("eng", "ita")) {
    if ($langs -notcontains $need) { throw "Tesseract senza '$need': $($langs -join ', ')" }
}

# --- ffmpeg -------------------------------------------------------------------
$ffDir = Join-Path $DestDir "ffmpeg"
if (-not (Test-Path -LiteralPath (Join-Path $ffDir "ffmpeg.exe"))) {
    $zip = Get-PinnedFile -Url $FfmpegUrl -Sha256 $FfmpegSha256 -FileName "ffmpeg-essentials_build.zip"
    $src = Join-Path $DestDir "ffmpeg-src"
    $srcFolder = Join-Path $src $FfmpegFolder
    if (-not (Test-Path -LiteralPath (Join-Path $srcFolder "bin\ffmpeg.exe"))) {
        Write-Host "estrazione in $src"
        Expand-Archive -LiteralPath $zip -DestinationPath $src -Force
    }
    if (-not (Test-Path -LiteralPath (Join-Path $srcFolder "bin\ffprobe.exe"))) {
        throw "struttura inattesa nello zip ffmpeg: manca $FfmpegFolder\bin\ffprobe.exe"
    }
    New-Item -ItemType Directory -Force -Path $ffDir | Out-Null
    foreach ($rel in @("bin\ffmpeg.exe", "bin\ffprobe.exe", "LICENSE", "README.txt")) {
        $file = Join-Path $srcFolder $rel
        if (-not (Test-Path -LiteralPath $file)) { throw "manca $rel nello zip ffmpeg" }
        Copy-Item -LiteralPath $file -Destination $ffDir -Force
    }
}

foreach ($exe in @("ffmpeg.exe", "ffprobe.exe")) {
    $want = $exe.Replace(".exe", "") + " version"
    $line = (& (Join-Path $ffDir $exe) -version | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or -not $line.StartsWith($want)) {
        throw "$exe non eseguibile: '$line'"
    }
    Write-Host "$exe : $line"
}

# --- output -------------------------------------------------------------------
Write-Host "VERSOCON_TESSERACT_DIR=$tess"
Write-Host "VERSOCON_FFMPEG_DIR=$ffDir"
if ($env:GITHUB_ENV) {
    Add-Content -LiteralPath $env:GITHUB_ENV -Value "VERSOCON_TESSERACT_DIR=$tess"
    Add-Content -LiteralPath $env:GITHUB_ENV -Value "VERSOCON_FFMPEG_DIR=$ffDir"
    Add-Content -LiteralPath $env:GITHUB_ENV -Value "VERSOCON_REQUIRE_ENGINES=1"
    Write-Host "esportate le variabili VERSOCON_* per lo spec PyInstaller"
}
