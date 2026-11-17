@echo off
rem Открыть собранный офлайн-архив в браузере (Windows).
setlocal
set "INDEX=%~dp0out\site\index.html"
if not exist "%INDEX%" (
  echo Сайт ещё не собран. Запустите: python scripts\04_build.py
  exit /b 1
)
start "" "%INDEX%"
