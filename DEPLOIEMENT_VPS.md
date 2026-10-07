# Mise en ligne sur un VPS

L'application tourne dans Docker, derrière **Caddy** qui obtient et renouvelle seul le certificat HTTPS (Let's Encrypt).
Une sauvegarde de la base est faite chaque nuit.

## Ce qu'il faut

- Un VPS **Ubuntu 22.04 ou 24.04** (Debian marche aussi) : 1 vCPU et 1 Go de RAM suffisent.
- Un **nom de domaine** ou sous-domaine (ex. `checklist.mondomaine.ma`) avec un enregistrement **A** qui pointe vers l'IP du VPS.
  À faire chez le fournisseur du domaine, de préférence avant l'installation (la propagation peut prendre quelques minutes).
- Les ports **80 et 443** ouverts (pare-feu de l'hébergeur s'il y en a un).

## 1. Installer (une seule commande)

Se connecter au VPS depuis le PC. Sous Windows : ouvrir **Terminal** (ou PowerShell) et taper :

```bash
ssh root@ADRESSE_IP_DU_VPS
```

Puis, sur le VPS :

```bash
curl -fsSL https://raw.githubusercontent.com/sifeddine-digital/sifeddine/main/deploy/install.sh | sudo bash
```

Le script pose trois questions : le **domaine**, l'**email** et le **mot de passe** de l'administrateur
(le mot de passe ne s'affiche pas pendant la frappe, c'est normal). Il installe ensuite Docker, l'application dans
`/opt/los-checklist`, démarre le tout, programme la sauvegarde de 2 h du matin et vérifie le HTTPS.

À la fin, ouvrir `https://le-domaine`, se connecter, puis menu **Importer la fiche Excel**.

Le script signale lui-même un domaine qui ne pointe pas encore vers le VPS : dans ce cas, corriger l'enregistrement A.
Le HTTPS s'active tout seul ensuite, sans rien relancer.

## 2. Reprendre les données saisies sur le PC (facultatif)

1. Sur le PC, dans l'application : menu **Sauvegarder les données**. Un fichier `LOS_sauvegarde_….sqlite3` est téléchargé.
2. L'envoyer sur le VPS, depuis le Terminal du PC (dossier Téléchargements) :
   ```bash
   scp LOS_sauvegarde_2026-10-07_1830.sqlite3 root@ADRESSE_IP_DU_VPS:/root/
   ```
3. Sur le VPS :
   ```bash
   cd /opt/los-checklist/deploy
   ./restaurer.sh /root/LOS_sauvegarde_2026-10-07_1830.sqlite3
   ```

La base du VPS est remplacée par celle du PC : on se connecte alors avec les **comptes du PC**. Le compte admin créé
pendant l'installation disparaît avec l'ancienne base ; une copie de celle-ci est gardée dans `sauvegardes/`.

## 3. Au quotidien

Toutes les commandes se lancent dans `/opt/los-checklist/deploy` (`cd /opt/los-checklist/deploy`).

| Besoin | Commande |
|---|---|
| Mettre à jour l'application | relancer la commande d'installation (les données ne sont pas touchées) |
| Sauvegarder maintenant | `./sauvegarde.sh` |
| Voir les sauvegardes | `ls -lh sauvegardes/` (les 30 dernières sont gardées) |
| Restaurer une sauvegarde | `./restaurer.sh sauvegardes/los_AAAA-MM-JJ_HHMMSS.sqlite3` |
| État des services | `docker compose ps` (les 2 services doivent être *running*) |
| Erreurs de l'application | `docker compose logs --tail 100 app` |
| Créer ou réinitialiser un admin | `docker compose exec app flask --app wsgi create-admin` |

Penser à récupérer de temps en temps une sauvegarde hors du serveur : depuis l'application (menu **Sauvegarder les données**),
ou depuis le PC avec `scp root@ADRESSE_IP_DU_VPS:/opt/los-checklist/deploy/sauvegardes/los_*.sqlite3 .`

## Dépannage

| Symptôme | Vérification |
|---|---|
| Le site ne répond pas | `docker compose ps`, puis `docker compose logs --tail 100 app` |
| Pas de HTTPS / erreur de certificat | le domaine pointe-t-il vers l'IP du VPS (`getent hosts le-domaine`) ? Ports 80/443 ouverts ? `docker compose logs --tail 50 caddy` |
| « Internal Server Error » | `docker compose logs --tail 100 app` : la dernière erreur Python y est affichée |
| Admin bloqué (mot de passe oublié) | `docker compose exec app flask --app wsgi create-admin` |
| « Trop de tentatives » à la connexion | attendre 15 minutes (8 essais ratés), ou réinitialiser le mot de passe |

## Installation manuelle (sans le script)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo git clone --branch main https://github.com/sifeddine-digital/sifeddine.git /opt/los-checklist
cd /opt/los-checklist/deploy
sudo cp .env.exemple .env && sudo chmod 600 .env
sudo nano .env        # DOMAINE, SECRET_KEY (openssl rand -hex 32), ADMIN_EMAIL, ADMIN_PASSWORD
sudo docker compose up -d --build
echo "0 2 * * * root /opt/los-checklist/deploy/sauvegarde.sh >> /opt/los-checklist/deploy/sauvegarde.log 2>&1" | sudo tee /etc/cron.d/los-checklist
```
