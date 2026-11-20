@echo off
rem Открыть собранный офлайн-архив в браузере (Windows).
rem Работает и из репозитория, и из корня смонтированного ISO.
setlocal
set "INDEX=%~dp0out\site\index.html"
if not exist "%INDEX%" set "INDEX=%~dp0index.html"
if not exist "%INDEX%" (
  echo Сайт не найден. Соберите: python scripts\04_build.py
  exit /b 1
)
start "" "%INDEX%"
