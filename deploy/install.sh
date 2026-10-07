#!/usr/bin/env bash
# LOS Checklist : installation (ou mise à jour) sur un VPS Ubuntu / Debian, en une commande.
#
#   curl -fsSL https://raw.githubusercontent.com/sifeddine-digital/sifeddine/main/deploy/install.sh | sudo bash
#
# Trois questions la première fois : domaine, email et mot de passe de l'administrateur.
# Relancer la même commande plus tard = mise à jour (le code est récupéré, les données restent).
# Sans questions : sudo DOMAINE=… ADMIN_EMAIL=… ADMIN_PASSWORD=… bash install.sh
#
# Ce que fait le script : Docker, récupération du code dans /opt/los-checklist, fichier deploy/.env
# (clé secrète générée), démarrage de l'application + Caddy (HTTPS Let's Encrypt automatique),
# sauvegarde de la base chaque nuit à 2 h (deploy/sauvegardes/, 30 copies gardées).
set -euo pipefail

REPO="${LOS_REPO:-https://github.com/sifeddine-digital/sifeddine.git}"
BRANCHE="${LOS_BRANCHE:-main}"
DIR="${LOS_DIR:-/opt/los-checklist}"
CRON_FILE="${LOS_CRON_FILE:-/etc/cron.d/los-checklist}"

etape()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()     { printf '\033[1;32m    %s\033[0m\n' "$*"; }
alerte() { printf '\033[1;33m    Attention : %s\033[0m\n' "$*"; }
stop()   { printf '\n\033[1;31mErreur : %s\033[0m\n' "$*" >&2; exit 1; }

# demander VARIABLE "question" [secret] : ne pose la question que si la variable n'est pas déjà fournie
demander() {
  local var=$1 question=$2 secret=${3:-} val=""
  [ -n "${!var:-}" ] && return 0
  { true </dev/tty; } 2>/dev/null || stop "$var manquant. Sans terminal, lancer : sudo $var=… bash install.sh"
  if [ -n "$secret" ]; then read -r -s -p "    $question : " val </dev/tty; echo; else read -r -p "    $question : " val </dev/tty; fi
  printf -v "$var" '%s' "$val"
}

[ "$(id -u)" -eq 0 ] || stop "lancer le script en root (avec sudo)."

# ------------------------------------------------------------------ 1. système
etape "Paquets système et Docker"
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq git curl openssl ca-certificates cron >/dev/null
else
  alerte "apt-get introuvable : vérifier que git, curl, openssl et cron sont installés."
fi
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
if command -v systemctl >/dev/null; then
  systemctl enable --now docker >/dev/null 2>&1 || true
  systemctl enable --now cron >/dev/null 2>&1 || true
fi
docker compose version >/dev/null 2>&1 || stop "« docker compose » n'est pas disponible (réinstaller Docker : curl -fsSL https://get.docker.com | sh)."
ok "$(docker --version)"

# ------------------------------------------------------------------ 2. code
etape "Code de l'application"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd || true)"
if [ -z "${LOS_DIR:-}" ] && [ -f "$SRC/app/__init__.py" ] && [ -f "$SRC/deploy/docker-compose.yml" ]; then
  DIR="$SRC"   # script lancé depuis un dossier déjà présent (git clone ou zip décompressé)
fi
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only -q || alerte "mise à jour du code impossible (fichiers modifiés à la main ?) : on garde la version actuelle."
elif [ -f "$DIR/app/__init__.py" ]; then
  ok "dossier existant (sans git) : pas de mise à jour automatique du code"
else
  git clone -q --depth 1 --branch "$BRANCHE" "$REPO" "$DIR"
fi
ok "$DIR"
cd "$DIR/deploy"
chmod +x sauvegarde.sh restaurer.sh 2>/dev/null || true

# ------------------------------------------------------------------ 3. configuration
etape "Configuration (deploy/.env)"
if [ -f .env ]; then
  ok "fichier .env existant conservé"
  DOMAINE="$(grep -E '^DOMAINE=' .env | head -1 | cut -d= -f2- | tr -d "'\"")"
  ADMIN_EMAIL="$(grep -E '^ADMIN_EMAIL=' .env | head -1 | cut -d= -f2- | tr -d "'\"")"
  NOUVELLE=0
else
  NOUVELLE=1
  demander DOMAINE "Domaine de l'application (ex. checklist.mondomaine.ma)"
  DOMAINE="$(printf '%s' "$DOMAINE" | tr '[:upper:]' '[:lower:]' | sed -E 's#^https?://##; s#/.*$##; s/[[:space:]]//g')"
  [[ "$DOMAINE" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] || stop "domaine invalide : « $DOMAINE »"
  demander ADMIN_EMAIL "Email de l'administrateur"
  ADMIN_EMAIL="$(printf '%s' "$ADMIN_EMAIL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  [[ "$ADMIN_EMAIL" == *@*.* ]] || stop "email invalide : « $ADMIN_EMAIL »"
  if [ -z "${ADMIN_PASSWORD:-}" ]; then
    demander ADMIN_PASSWORD "Mot de passe administrateur (8 caractères minimum)" secret
    CONFIRM=""; demander CONFIRM "Retaper le mot de passe" secret
    [ "$ADMIN_PASSWORD" = "$CONFIRM" ] || stop "les deux mots de passe sont différents."
  fi
  [ "${#ADMIN_PASSWORD}" -ge 8 ] || stop "mot de passe trop court (8 caractères minimum)."
  [[ "$ADMIN_PASSWORD" != *"'"* ]] || stop "le mot de passe ne doit pas contenir d'apostrophe (')."
  ( umask 077
    { echo "# Créé par install.sh le $(date '+%d/%m/%Y %H:%M') - ne pas partager ce fichier."
      echo "DOMAINE=$DOMAINE"
      echo "SECRET_KEY=$(openssl rand -hex 32)"
      echo "ADMIN_EMAIL=$ADMIN_EMAIL"
      echo "ADMIN_PASSWORD='$ADMIN_PASSWORD'"
    } > .env )
  ok "domaine $DOMAINE, administrateur $ADMIN_EMAIL"
fi

# ------------------------------------------------------------------ 4. réseau
etape "Vérification du domaine et du pare-feu"
IP_VPS="$(curl -fsS4 --max-time 8 https://api.ipify.org 2>/dev/null || true)"
IPS_DOMAINE="$(getent ahostsv4 "$DOMAINE" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')"
CIBLE="$IP_VPS"; [ -n "$CIBLE" ] || CIBLE="l'adresse IP du VPS"
if [ -z "$IPS_DOMAINE" ]; then
  alerte "le domaine $DOMAINE ne pointe vers aucune adresse. Créer chez le fournisseur du domaine un enregistrement A vers $CIBLE : le HTTPS s'activera tout seul ensuite."
elif [ -n "$IP_VPS" ] && [[ " $IPS_DOMAINE " != *" $IP_VPS "* ]]; then
  alerte "$DOMAINE pointe vers $IPS_DOMAINE mais ce VPS a l'adresse $IP_VPS. Corriger l'enregistrement A : le HTTPS ne marchera qu'après."
else
  ok "$DOMAINE → ${IPS_DOMAINE% }"
fi
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
  ok "pare-feu ufw : ports 80 et 443 ouverts"
else
  ok "ufw inactif : vérifier que les ports 80 et 443 sont ouverts dans le pare-feu de l'hébergeur"
fi

# ------------------------------------------------------------------ 5. démarrage
etape "Construction et démarrage (2 à 5 minutes la première fois)"
docker compose up -d --build --remove-orphans
for _ in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=3)" >/dev/null 2>&1; then
    ok "l'application répond"; break
  fi
  sleep 3
done
docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login', timeout=3)" >/dev/null 2>&1 \
  || { docker compose logs --tail 40 app; stop "l'application ne démarre pas (voir les lignes ci-dessus)."; }

# le compte admin est créé au premier démarrage : le mot de passe n'a plus rien à faire dans .env
if [ "$NOUVELLE" -eq 1 ] && docker compose exec -T -e LOS_EMAIL="$ADMIN_EMAIL" app python -c "
import os, sqlite3, sys
c = sqlite3.connect('/data/los.sqlite3')
sys.exit(0 if c.execute(\"SELECT 1 FROM users WHERE email = ? AND role = 'admin'\", (os.environ['LOS_EMAIL'],)).fetchone() else 1)"; then
  sed -i 's/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=/' .env
  ok "compte administrateur $ADMIN_EMAIL prêt (mot de passe retiré du fichier .env)"
fi

# ------------------------------------------------------------------ 6. sauvegarde quotidienne
etape "Sauvegarde automatique"
mkdir -p "$(dirname "$CRON_FILE")"
cat > "$CRON_FILE" <<EOF
# LOS Checklist : copie de la base chaque nuit à 2 h (30 dernières copies dans $DIR/deploy/sauvegardes)
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 2 * * * root $DIR/deploy/sauvegarde.sh >> $DIR/deploy/sauvegarde.log 2>&1
EOF
chmod 644 "$CRON_FILE"
ok "tous les jours à 2 h → $DIR/deploy/sauvegardes/"

# ------------------------------------------------------------------ 7. HTTPS
etape "Certificat HTTPS"
HTTPS_OK=0
for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 5 "https://$DOMAINE/login" 2>/dev/null; then HTTPS_OK=1; break; fi
  sleep 3
done
if [ "$HTTPS_OK" -eq 1 ]; then ok "https://$DOMAINE répond"
else alerte "le HTTPS n'est pas encore actif. Il s'active tout seul dès que le domaine pointe vers ce VPS et que les ports 80/443 sont ouverts (suivi : cd $DIR/deploy && docker compose logs caddy)."
fi

cat <<EOF

$(printf '\033[1;32m')LOS Checklist est installée.$(printf '\033[0m')
  Adresse          : https://$DOMAINE
  Administrateur   : $ADMIN_EMAIL
  Première chose   : se connecter, puis menu « Importer la fiche Excel ».

  Mettre à jour    : relancer la même commande d'installation
  Sauvegarde       : cd $DIR/deploy && ./sauvegarde.sh
  Restaurer        : cd $DIR/deploy && ./restaurer.sh chemin/vers/fichier.sqlite3
  Journaux         : cd $DIR/deploy && docker compose logs --tail 100 app
  Admin oublié     : cd $DIR/deploy && docker compose exec app flask --app wsgi create-admin
EOF
