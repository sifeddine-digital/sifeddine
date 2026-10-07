# LOS Checklist — application terrain + tableau de bord

Application web (mobile d'abord) qui remplace la fiche Excel **« LOS Inventaire & Checklist LS »** :

- **Superviseurs** : connexion par email + mot de passe, liste de *leurs* stations, checklist hebdomadaire sur téléphone
  (gros boutons Oui / Non / N/A, score calculé en direct, « Tout Oui » par bloc, reprise des réponses de la semaine
  précédente, brouillon sauvegardé dans le téléphone en cas de coupure réseau, position GPS enregistrée à l'envoi).
  Inventaire équipements et stock : saisie **mensuelle** (pré-remplie avec le dernier inventaire connu).
- **Admin** : tableau de bord (complétion, scores par secteur / superviseur / bloc, stations critiques, non faites,
  points les plus souvent en « Non », évolution 8 semaines, plan d'actions), gestion des comptes, **choix des stations
  affectées à chaque superviseur**, verrouillage / renvoi d'une checklist pour correction, seuils de scoring.
- **Export Excel** : mêmes onglets et même style que la fiche (`Checklist`, `Invt_Eqmt`, `Invt_Stck` avec formules,
  couleurs conditionnelles et listes déroulantes) + `Dashboard` (KPI, tableaux, 4 graphiques), `Historique`
  (stations × semaines) et `Plan d'actions` (avec colonne de suivi).

Les règles de scoring sont celles de la fiche : % par bloc = Oui / (Oui + Non) (N/A ignoré), un « Non »
éliminatoire ⇒ **Critique**, sinon **À corriger** si global < 85 % ou un bloc < 70 %, sinon **Conforme**
(seuils modifiables dans l'app).

## Sur un PC Windows (le plus simple)

1. Installer Python depuis [python.org](https://www.python.org/downloads/) en cochant **« Add python.exe to PATH »**.
2. Double-cliquer sur **`lancer.bat`** : la première fois, il installe tout et demande l'email et le mot de passe admin.
3. Le navigateur s'ouvre sur `http://localhost:8000` → se connecter → **Importer la fiche Excel**.

Les données restent dans le dossier `instance\` (à sauvegarder).

## Démarrage rapide (local, ligne de commande)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
flask --app wsgi create-admin                       # crée le compte admin (email + mot de passe)
flask --app wsgi import-fiche "LOS_Inventaire_ Checklist_LS_v11.xlsx"   # importe les 120 stations + données
flask --app wsgi run --host 0.0.0.0 --port 8000
```

L'import est aussi disponible dans l'app : menu admin → **Importer la fiche Excel**.

## Mise en ligne

### Essai rapide sur Render (sans terminal)

1. Créer un compte sur [render.com](https://render.com) avec « Sign in with GitHub ».
2. **New → Blueprint**, choisir le dépôt `sifeddine` : Render lit `render.yaml`.
3. Saisir `ADMIN_EMAIL` et `ADMIN_PASSWORD` (8 caractères min.) puis **Apply**.
4. Ouvrir l'adresse `https://los-checklist-xxxx.onrender.com`, se connecter, puis **Importer la fiche Excel**.

⚠️ Le plan gratuit n'a pas de disque permanent : les données sont effacées quand le service redémarre
(après ~15 min sans visite). Parfait pour tester ; pour l'utilisation réelle, ajouter un disque Render
(`DATABASE_PATH=/var/data/los.sqlite3`, plan payant) ou utiliser PythonAnywhere.

### Hébergement permanent sur un VPS

Voir **[DEPLOIEMENT_VPS.md](DEPLOIEMENT_VPS.md)** : Docker + HTTPS automatique (Caddy) + sauvegarde quotidienne,
fichiers prêts dans `deploy/`.

### Autres hébergements

L'app utilise SQLite (un seul fichier) : il faut un hébergement avec **disque persistant**.

- **PythonAnywhere** (simple, plan gratuit possible) : cloner le dépôt, créer un virtualenv, `pip install -r requirements.txt`,
  configurer l'app WSGI sur `wsgi.py`, puis lancer `create-admin` dans une console.
- **VPS / Docker** : `docker build -t los . && docker run -d -p 8000:8000 -v los-data:/data -e SECRET_KEY=... los`
  (mettre derrière HTTPS, ex. Caddy ou Nginx).

Variables d'environnement : `SECRET_KEY` (sinon générée dans `instance/`), `DATABASE_PATH`,
`SESSION_COOKIE_SECURE=1` en HTTPS. Sauvegarde : copier le fichier `los.sqlite3`.

Les superviseurs peuvent **« Ajouter à l'écran d'accueil »** depuis Chrome/Safari : l'app s'ouvre alors comme une application.

## Nouveautés v2

- **Checklist hebdomadaire mise en avant** : carte « N checklists à faire avant dimanche (J-x) », bouton
  « Commencer / Continuer », rappel des checklists de la **semaine dernière** à rattraper, badge rouge dans le menu,
  historique des 4 dernières semaines (points de couleur) pour chaque station. Inventaire & stock restent mensuels.
- **Export Excel en un clic** : *Dernier état* (la dernière checklist de chaque station, quelle que soit la semaine),
  *Cette semaine*, *Semaine dernière*, ou export personnalisé (une semaine, une période du … au …, par secteur et par superviseur).
- **Tableau de bord PC** : menu latéral, tableau « Régularité hebdomadaire » (8 semaines × superviseur),
  bouton **Relancer** qui ouvre WhatsApp avec la liste des stations restantes du superviseur.
- **Sécurité** : mot de passe provisoire à changer à la première connexion, changement / réinitialisation du mot de passe
  = déconnexion des autres appareils, blocage après 8 essais ratés (15 min), en-têtes de sécurité (CSP sans JavaScript
  inline, anti-iframe, pas de cache des pages privées), protection contre l'injection de formules dans l'export Excel,
  **journal d'activité** (connexions, envois, affectations, exports…) et **sauvegarde** de la base en un clic.

## Règles d'accès

| | Superviseur | Admin |
|---|---|---|
| Voir / remplir | uniquement ses stations | toutes |
| Modifier une checklist | semaine en cours + précédente, si non verrouillée | toujours |
| Inventaire / stock | mois en cours + précédent | toujours |
| Tableau de bord, export, comptes, affectations | — | ✓ |

## Tests

```bash
pip install pytest && pytest -q
```

## Corrections apportées par rapport à la fiche v11

- `Checklist` X/Y (*Équipements dotés / manquants*) pointaient vers un classeur externe `[1]` et la plage `F:W`
  (qui inclut « Baie ? » / « SHSC ? » et oublie *Contrôleur de pression* / *Kit chandelle*) → l'export pointe vers
  l'onglet `Invt_Eqmt` du même fichier, plage `H:Y` (blocs 1 et 2).
- `Invt_Stck` : la mise en forme « écart > 5 % » référençait `#REF!` → colonnes *Stock physique*, *Stock système*
  et *Écart %* calculé, comme le décrit la consigne de l'onglet.

## Idées d'évolution

1. **Photos** sur chaque « Non » (preuve + suivi avant / après).
2. **Rappels automatiques** (email / SMS) le jeudi aux superviseurs qui n'ont pas terminé leur semaine
   (la relance WhatsApp manuelle existe déjà dans le tableau de bord).
3. **Suivi des actions** : chaque action devient une tâche « ouverte → clôturée », vérifiée à la visite suivante.
4. **Rôle « manager » en lecture seule** (direction, Vivo Energy) pour consulter le tableau de bord sans modifier.
5. **Classement des stations / superviseurs** et badge « station du mois ».
6. **Mode hors-ligne complet** (service worker) pour les zones sans réseau.
