#!/bin/sh
# Remet en place une sauvegarde de la base :
#   ./restaurer.sh sauvegardes/los_AAAA-MM-JJ_HHMM.sqlite3
# Marche aussi avec le fichier téléchargé depuis l'application (menu « Sauvegarder les données »),
# par exemple pour reprendre sur le VPS les données saisies sur le PC.
# La base actuelle est d'abord sauvegardée dans sauvegardes/.
set -e
cd "$(dirname "$0")"
F="${1:-}"
[ -n "$F" ] || { echo "Usage : ./restaurer.sh fichier.sqlite3"; exit 1; }
[ -f "$F" ] || { echo "Fichier introuvable : $F"; exit 1; }
head -c 16 "$F" | grep -q "SQLite format 3" || { echo "Ce fichier n'est pas une base de données LOS (SQLite)."; exit 1; }
F="$(cd "$(dirname "$F")" && pwd)/$(basename "$F")"

echo "1/3 Sauvegarde de la base actuelle…"
./sauvegarde.sh || echo "    (pas de base actuelle à sauvegarder)"
echo "2/3 Remplacement de la base…"
docker compose stop app
# on retire aussi les fichiers -wal / -shm de l'ancienne base, sinon SQLite les rejouerait sur la nouvelle
docker compose run --rm --no-deps -v "$F:/restaurer.sqlite3:ro" --entrypoint sh app -c \
  'rm -f /data/los.sqlite3-wal /data/los.sqlite3-shm && cp /restaurer.sqlite3 /data/los.sqlite3'
echo "3/3 Redémarrage…"
docker compose start app
echo "Base restaurée depuis $F"
