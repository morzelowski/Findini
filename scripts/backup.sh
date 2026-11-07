#!/usr/bin/env bash
# Kopia zapasowa Findini: baza (pg_dump, format custom) + wolumen zdjęć (tar.gz).
# Użycie: ./scripts/backup.sh [katalog_docelowy]     (domyślnie backups/RRRRMMDD-HHMMSS)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
TS=$(date +%Y%m%d-%H%M%S)
OUT=${1:-backups/$TS}
mkdir -p "$OUT"
echo "→ Zrzut bazy do $OUT/db.dump"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-findini}" -Fc "${POSTGRES_DB:-findini}" > "$OUT/db.dump"
echo "→ Archiwum zdjęć do $OUT/photos.tgz"
docker compose run --rm --no-deps -v "$(pwd)/$OUT:/backup" --entrypoint sh api -c "tar czf /backup/photos.tgz -C /data photos"
( cd "$OUT" && shasum -a 256 db.dump photos.tgz > SHA256SUMS )
echo "Gotowe: $(du -sh "$OUT" | cut -f1) w $OUT (zawiera dane prywatne — przechowuj zaszyfrowane, z ograniczonym dostępem)"
