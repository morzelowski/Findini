# PostgreSQL 17 + pgvector 0.8.7 (obraz wieloplatformowy, także arm64) + PostGIS 3 z repozytorium PGDG.
FROM pgvector/pgvector:0.8.7-pg17-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
 && rm -rf /var/lib/apt/lists/*
