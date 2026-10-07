@echo off
chcp 65001 >nul
title LOS Checklist
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python n'est pas installe sur ce PC.
  echo  1. Installez-le depuis la page qui va s'ouvrir.
  echo  2. IMPORTANT : cochez "Add python.exe to PATH" pendant l'installation.
  echo  3. Relancez ce fichier lancer.bat.
  start "" https://www.python.org/downloads/
  pause
  exit /b
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  Installation - premiere fois seulement, 1 a 2 minutes...
  python -m venv .venv || goto erreur
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto erreur
)

if not exist "instance\admin.ok" (
  echo.
  echo  Creation de votre compte administrateur
  echo  ---------------------------------------
  ".venv\Scripts\flask.exe" --app wsgi create-admin || goto erreur
  echo ok> "instance\admin.ok"
)

echo.
echo  L'application est lancee : http://localhost:8000
echo  Gardez cette fenetre ouverte. Fermez-la pour arreter l'application.
echo.
start "" http://localhost:8000
".venv\Scripts\flask.exe" --app wsgi run --port 8000
pause
exit /b

:erreur
echo.
echo  Une erreur s'est produite. Faites une capture de cette fenetre et envoyez-la.
pause
