#!/usr/bin/env bash
# Odtworzenie Findini z kopii: ./scripts/restore.sh backups/RRRRMMDD-HHMMSS [--yes]
# UWAGA: nadpisuje bieżącą bazę i zdjęcia. Bez --yes pyta o potwierdzenie.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
SRC=${1:?Podaj katalog kopii}
( cd "$SRC" && shasum -a 256 -c SHA256SUMS )
if [ "${2:-}" != "--yes" ]; then
  read -r -p "To nadpisze bieżące dane Findini danymi z $SRC. Kontynuować? [tak/N] " ans
  [ "$ans" = "tak" ] || { echo "Przerwano."; exit 1; }
fi
docker compose stop api
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-findini}" -d "${POSTGRES_DB:-findini}" --clean --if-exists --no-owner < "$SRC/db.dump"
docker compose run --rm --no-deps -v "$(pwd)/$SRC:/backup:ro" --entrypoint sh api -c "rm -rf /data/photos/* && tar xzf /backup/photos.tgz -C /data"
docker compose start api
echo "Odtworzono z $SRC."
