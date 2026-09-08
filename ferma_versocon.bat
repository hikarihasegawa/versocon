@echo off
setlocal
set PORT=8321

REM --- l'app risponde davvero su questa porta? ---
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%PORT%/api/config -UseBasicParsing -TimeoutSec 2).StatusCode } catch { }" | findstr /i 200 >nul
if errorlevel 1 (
  echo L'app non risponde su http://127.0.0.1:%PORT% (non sembra in esecuzione).
  goto :eof
)

REM --- ferma il processo in ascolto sulla porta ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /c:":%PORT%" /c:"LISTENING"') do (
  taskkill /PID %%p /T /F >nul 2>&1
  echo Processo PID %%p fermato.
)

REM --- sicurezza: chiudi eventuale finestra "VersoCon" residua ---
taskkill /FI "WINDOWTITLE eq VersoCon*" /F >nul 2>&1
echo App fermata.
endlocal
