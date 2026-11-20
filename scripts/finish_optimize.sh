#!/usr/bin/env bash
# Дожидается WebP-конвертации, затем VACUUM, очистка старых hardlinks и пересборка.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/work/optimize_final.log"
exec >>"$LOG" 2>&1
echo "[$(date -Is)] ждём завершения optimize_media.py"
for _ in $(seq 1 1440); do
  if ! pgrep -f "[o]ptimize_media.py" >/dev/null; then break; fi
  sleep 60
done
echo "[$(date -Is)] WebP завершён, VACUUM"
.venv/bin/python - <<'PY'
import sqlite3
c=sqlite3.connect('data/archive.sqlite', timeout=60)
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
c.execute("VACUUM")
c.close()
print("vacuum done")
PY
echo "[$(date -Is)] удаляю старые hardlinks media"
rm -rf out/site/media
echo "[$(date -Is)] пересборка"
.venv/bin/python scripts/04_build.py
echo "[$(date -Is)] готово"
du -sh data out .git 2>/dev/null || true
df -h . | tail -1
