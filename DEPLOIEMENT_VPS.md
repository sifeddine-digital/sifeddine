# Mise en ligne sur un VPS

Ce guide installe LOS Checklist sur un serveur Linux (Ubuntu 22.04 ou 24.04) avec :

- l'application dans un conteneur Docker (gunicorn, 2 processus) ;
- **Caddy** devant, qui obtient et renouvelle tout seul le certificat HTTPS (Let's Encrypt) ;
- une **sauvegarde quotidienne** de la base de données.

Il faut : un VPS (1 vCPU / 1 Go de RAM suffisent), un nom de domaine ou sous-domaine
(ex. `checklist.mondomaine.ma`) dont l'enregistrement **A** pointe vers l'IP du VPS, et les ports 80 et 443 ouverts.

## 1. Préparer le serveur

```bash
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # puis se déconnecter / reconnecter
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw --force enable
```

## 2. Récupérer l'application

```bash
git clone https://github.com/sifeddine-digital/sifeddine.git los-checklist
cd los-checklist/deploy
cp .env.exemple .env
nano .env
```

Dans `.env` :

| Variable | Valeur |
|---|---|
| `DOMAINE` | le domaine, ex. `checklist.mondomaine.ma` |
| `SECRET_KEY` | une longue chaîne aléatoire : `openssl rand -hex 32` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | le premier compte administrateur (8 caractères minimum) |

## 3. Démarrer

```bash
docker compose up -d --build
docker compose logs -f app        # « Booting worker » = l'application tourne (Ctrl+C pour quitter)
```

Ouvrir `https://checklist.mondomaine.ma`, se connecter avec `ADMIN_EMAIL` / `ADMIN_PASSWORD`,
puis **Importer la fiche Excel** depuis le menu.

## 4. Sauvegarde automatique (tous les jours à 2 h)

```bash
crontab -e
# ajouter la ligne (adapter le chemin) :
0 2 * * * /home/ubuntu/los-checklist/deploy/sauvegarde.sh >> /home/ubuntu/los-checklist/deploy/sauvegarde.log 2>&1
```

Les copies sont dans `deploy/sauvegardes/` (30 dernières gardées). Penser à en récupérer une de temps en temps
sur un autre support. Depuis l'application, l'admin peut aussi télécharger une copie : menu **Sauvegarder les données**.

**Restaurer** une sauvegarde :

```bash
docker compose cp sauvegardes/los_AAAA-MM-JJ_HHMM.sqlite3 app:/data/los.sqlite3
docker compose restart app
```

## 5. Mettre à jour l'application

```bash
cd ~/los-checklist && git pull
cd deploy && docker compose up -d --build
```

Les données (volume `los-data`) ne sont pas touchées par une mise à jour.

## Dépannage

| Symptôme | Vérification |
|---|---|
| Le site ne répond pas | `docker compose ps` (les 2 services doivent être *running*), `docker compose logs app` |
| Pas de HTTPS / erreur de certificat | le domaine pointe-t-il vers l'IP du VPS ? ports 80/443 ouverts ? `docker compose logs caddy` |
| Admin bloqué (mot de passe oublié) | `docker compose exec app flask --app wsgi create-admin` (crée ou réinitialise un admin) |
| « Internal Server Error » | `docker compose logs app --tail 100` : la dernière erreur Python y est affichée |
