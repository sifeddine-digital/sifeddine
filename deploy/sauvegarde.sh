#!/bin/sh
# Sauvegarde quotidienne de la base (à lancer par cron) : garde les 30 dernières copies.
set -e
cd "$(dirname "$0")"
mkdir -p sauvegardes
docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/data/los.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close()"
docker compose cp app:/data/backup.sqlite3 "sauvegardes/los_$(date +%Y-%m-%d_%H%M).sqlite3"
ls -1t sauvegardes/los_*.sqlite3 | tail -n +31 | xargs -r rm --
