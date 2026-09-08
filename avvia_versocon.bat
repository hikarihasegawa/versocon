@echo off
setlocal
set PORT=8321
cd /d "%~dp0"

REM --- gia' in esecuzione? (probe HTTP reale, non netstat) ---
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%PORT%/api/config -UseBasicParsing -TimeoutSec 2).StatusCode } catch { }" | findstr /i 200 >nul
if not errorlevel 1 (
  echo App gia' in esecuzione su http://127.0.0.1:%PORT%
  start "" "http://127.0.0.1:%PORT%"
  goto :eof
)

REM --- avvio in finestra (dev: errori visibili, Ctrl+C per fermare) ---
echo Avvio VersoCon su http://127.0.0.1:%PORT% ...
start "VersoCon" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --log-level warning"

REM --- attendi ready (max ~20s) ---
set /a I=0
:wait
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://127.0.0.1:%PORT%/api/config -UseBasicParsing -TimeoutSec 1) | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto :ok
ping -n 2 127.0.0.1 >nul
set /a I+=1
if %I% lss 20 goto :wait
echo ATTENZIONE: avvio non confermato (controlla la finestra "VersoCon").
:ok
start "" "http://127.0.0.1:%PORT%"
echo Fatto. Browser aperto su http://127.0.0.1:%PORT%
endlocal
