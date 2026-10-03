@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>nul
if errorlevel 1 goto no_python
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed
:run
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failed
exit /b 0
:install_failed
rmdir /s /q .venv
:failed
echo.
echo Setup or launch failed. Send the text above to Jack's ChatGPT conversation.
pause
exit /b 1
:no_python
echo Install Python 3.12 or 3.13 for Windows from https://www.python.org/downloads/windows/
echo Include the Python launcher when installing, then open Launch.bat again.
pause
exit /b 1
