#!/usr/bin/env bash
# Собирает ISO с офлайн-архивом. Внутри — статический сайт и view.*-запускаторы.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SITE="$ROOT/out/site"
STAGE="$ROOT/work/iso-root"
ISO="$ROOT/out/minkara-archive.iso"

if [ ! -f "$SITE/index.html" ]; then
  echo "Сайт не собран: сначала выполните make build"
  exit 1
fi
if ! command -v genisoimage >/dev/null 2>&1; then
  echo "Нужен genisoimage (пакет genisoimage / mkisofs)"
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -al "$SITE/." "$STAGE/"
cp packaging/README-ISO.txt "$STAGE/README.txt"
cp view.sh view.command view.bat "$STAGE/"
chmod +x "$STAGE/view.sh" "$STAGE/view.command"

echo "Собираю ISO…"
genisoimage -quiet -R -J -joliet-long -V MINKARA_ARCHIVE \
  -o "$ISO" "$STAGE"
rm -rf "$STAGE"
ls -lh "$ISO"
echo "Готово: $ISO"
