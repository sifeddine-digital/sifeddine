# LOS Checklist : contexte pour Claude

Ce fichier explique l'application à un assistant qui la découvre (mise en ligne, maintenance, évolutions).
Les explications pour les utilisateurs sont dans `docs/LOS_Checklist_Guide_utilisation.pdf`.

## Le propriétaire

- Il écrit en **darija marocaine en lettres latines** : lui répondre en darija, simplement.
  L'interface de l'application et la documentation restent **en français**.
- Il n'est pas développeur. Sur un serveur, lui donner des commandes à copier-coller **une par une**,
  dire ce qu'on attend comme résultat, et lui demander de renvoyer la sortie (ou une capture) s'il y a une erreur.
- Ne jamais lui demander d'envoyer un mot de passe, une clé ou le contenu de `deploy/.env` dans le chat.

## À quoi sert l'application

Elle remplace la fiche Excel « LOS Inventaire & Checklist LS » (supervision lubrifiants Shell / Vivo Energy Maroc,
120 stations, 6 secteurs : 01 Casa Nord, 02 Casa Sud, 03 Rabat - Khemisset, 04 Kenitra - Tanger, 05 Agadir,
08 Maroc Centre - Marrakech).

- **Superviseurs** (téléphone) : chaque semaine, une checklist par station (20 points : 3 éliminatoires + 6 blocs) ;
  chaque mois, l'inventaire des équipements et le stock de lubrifiants. Ils ne voient que leurs stations.
- **Administrateur** (PC) : tableau de bord, suivi et relance WhatsApp des superviseurs, affectation des stations,
  comptes, seuils, import de la fiche, **export Excel au format exact de la fiche** (+ Dashboard, Historique,
  Plan d'actions), sauvegarde de la base.

## Technique

- Python 3.12, **Flask 3.1** (3 blueprints), **SQLite** (WAL), Jinja2, openpyxl, gunicorn. CSS/JS maison, aucun CDN.
- En production : Docker (`Dockerfile`, gunicorn 2 processus `--preload`) + **Caddy** (HTTPS Let's Encrypt automatique)
  via `deploy/docker-compose.yml`. La base est dans le volume Docker `los-data` (`/data/los.sqlite3`).

| Fichier | Rôle |
|---|---|
| `app/__init__.py` | `create_app` : config, ProxyFix (`BEHIND_PROXY=1`), CSRF, en-têtes de sécurité, admin initial depuis `ADMIN_EMAIL`/`ADMIN_PASSWORD`, commandes `flask create-admin` et `flask import-fiche` |
| `app/db.py` | schéma SQLite, migrations (ajout de colonnes tolérant), `query`/`execute`, réglages, seuils |
| `app/referentiel.py` | points de contrôle (ÉLIM 1-3, P/S/E/A/H/C), équipements, listes de choix |
| `app/scoring.py` | calcul des scores et statuts, semaines ISO (`week_start` = lundi), mois |
| `app/auth.py` | connexion, sessions, blocage après 8 échecs / 15 min (en mémoire), mot de passe provisoire obligatoire à changer |
| `app/terrain.py` | écrans superviseur : `/semaine`, `/checklist/<station>/<lundi>`, `/mois`, `/inventaire/…`, `/stock/…` |
| `app/admin.py` | écrans admin sous `/admin` : tableau de bord, stations, superviseurs, import, export, seuils, sauvegarde |
| `app/stats.py` | agrégats du tableau de bord (web et Excel), relances WhatsApp (`wa_number`) |
| `app/export_xlsx.py` | export Excel : onglets `Dashboard`, `Checklist` (colonnes A:AY de la fiche, avec formules), `Invt_Eqmt`, `Invt_Stck`, `Historique`, `Plan d'actions` |
| `app/importer.py` | import de la fiche Excel (stations reconnues par code Ship-to) |
| `app/templates/` | `base.html` (menu, barre du bas mobile), écrans terrain, `admin/…` |
| `app/static/` | `app.css`, `app.js`, logo `img/vivo-energy.svg`, `manifest.json` |
| `tests/test_app.py` | 18 tests (droits, checklist, export, sécurité, rendu de chaque page pour les deux rôles) |
| `deploy/` | `install.sh` (installation VPS en une commande), `docker-compose.yml`, `Caddyfile`, `sauvegarde.sh`, `restaurer.sh`, `.env.exemple` |
| `lancer.bat` | lancement sur un PC Windows (données dans `instance\`) |

### Données

- `users` (role `admin`/`superviseur`, `must_change`), `stations` (`ship_to` unique, `secteur`, `supervisor_id`, `active`),
  `checklists` (une par station et par semaine, `data` JSON : `answers`, `constats`, `actions`, `responsable`,
  `commentaire`, `visit_date` ; `status` brouillon/envoye, `locked`, position GPS à l'envoi),
  `inventaires` et `stocks` (un par station et par mois), `settings` (seuils).
- Pas de journal d'activité : il a été **retiré à la demande du propriétaire** (plus aucune adresse IP enregistrée ;
  la table `journal` d'une ancienne version est supprimée au démarrage). Ne pas réintroduire de traçage sans qu'il le demande.

### Règles métier (identiques à la fiche)

- Score d'un bloc = Oui ÷ (Oui + Non), N/A ignoré. Score global = même calcul sur les 17 points des blocs (ÉLIM non compris).
- Statut : un « Non » éliminatoire ⇒ **Critique** ; sinon **À corriger** si global < 85 % ou un bloc < 70 % ; sinon **Conforme**.
  Seuils modifiables (`/admin/settings`, tout est recalculé).
- Un « Non » dans un bloc rend son constat obligatoire ; l'envoi exige les 20 réponses et la date de visite.
- Un superviseur modifie la semaine en cours et la précédente (si non verrouillée) ; inventaire/stock : mois en cours et précédent.
- Export « dernier état » = la dernière checklist envoyée de chaque station, quelle que soit la semaine.

### Pièges connus

- Dans `base.html`, les variables internes sont préfixées (`_me`, `_ep`, `_nav`…) : un `{% set %}` de premier niveau
  dans le layout écrase les variables du même nom passées aux pages (cause d'une ancienne erreur 500).
- CSP stricte : **aucun JavaScript inline** (ni `<script>` dans les pages, ni `onclick=`) ; tout passe par `app.js` et des attributs `data-…`.
- Gunicorn garde les templates en cache : redémarrer après une modification.
- Les dates `datetime('now')` de SQLite sont en UTC.
- Valeurs saisies exportées vers Excel : protégées contre l'injection de formules (ne pas retirer).

## Commandes utiles

En local :

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest
pytest -q
flask --app wsgi create-admin
flask --app wsgi run --port 8000
```

Sur le VPS (dossier `/opt/los-checklist/deploy`) :

| Besoin | Commande |
|---|---|
| Installer / mettre à jour | `curl -fsSL https://raw.githubusercontent.com/sifeddine-digital/sifeddine/main/deploy/install.sh \| sudo bash` |
| État des services | `docker compose ps` |
| Erreurs de l'application | `docker compose logs --tail 100 app` |
| Certificat HTTPS | `docker compose logs --tail 50 caddy` |
| Sauvegarde immédiate | `./sauvegarde.sh` (copies dans `sauvegardes/`, cron chaque nuit à 2 h) |
| Restaurer / reprendre les données du PC | `./restaurer.sh fichier.sqlite3` |
| Créer ou réinitialiser un admin | `docker compose exec app flask --app wsgi create-admin` |
| Importer la fiche en ligne de commande | `docker compose cp fiche.xlsx app:/tmp/f.xlsx && docker compose exec app flask --app wsgi import-fiche /tmp/f.xlsx` |

`deploy/.env` (droits 600) : `DOMAINE`, `SECRET_KEY` (générée), `ADMIN_EMAIL`, `ADMIN_PASSWORD`
(vidé par `install.sh` une fois le compte créé). Voir `DEPLOIEMENT_VPS.md` pour la procédure complète et le dépannage.

## Méthode de travail

- Lancer `pytest -q` avant tout commit ; garder les tests verts et en ajouter pour chaque correction.
- Vérifier les écrans en largeur téléphone (390 px et 320 px) et PC : aucune barre de défilement horizontale.
- Le dépôt GitHub `sifeddine-digital/sifeddine` est **public** : n'y mettre ni mot de passe, ni `.env`, ni base de données, ni fiche Excel réelle.
