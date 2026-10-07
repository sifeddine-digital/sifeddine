"""Référentiel de la fiche « LOS Inventaire & Checklist LS » (v11).

Toutes les listes (points de contrôle, équipements, options) sont définies ici
une seule fois : les formulaires, le scoring et l'export Excel les relisent.
"""

REPONSES = ("Oui", "Non", "N/A")

# Points éliminatoires : un seul « Non » => statut « Critique ».
ELIMINATOIRES = [
    ("elim1", "ÉLIM 1 — Aucune fuite d'huile"),
    ("elim2", "ÉLIM 2 — Bacs huile usagée fermés"),
    ("elim3", "ÉLIM 3 — Aucun danger"),
]

E1_AIDE = (
    "Pont élévateur, vidangeurs (aspiration / gravité / mixte), pompe à graisse, "
    "récupérateur d'huile, enrouleur d'air, cric rouleur. Oui = chaque équipement "
    "doté est fonctionnel le jour de la visite, sans panne récurrente, et au moins "
    "un vidangeur est opérationnel. Un seul élément indisponible ⇒ Non."
)
E2_AIDE = (
    "Outil de diagnostic, servante, caisse à outils, clés coiffes, lampe "
    "d'inspection, tournevis, cloches filtre à huile, clé dynamométrique, "
    "contrôleur de pression, kit chandelle. Oui = tous les outils dotés sont "
    "présents, complets et en état. Un outil manquant ⇒ Non (le nommer dans le constat)."
)

# Blocs notés. Chaque bloc : clé, titre, liste (code, libellé, aide).
BLOCS = [
    ("proprete", "1. PROPRETÉ", [
        ("P1", "P1 — Baie propre", ""),
        ("P2", "P2 — Présentoir îlot propre", ""),
        ("P3", "P3 — Rayon shop propre", ""),
    ]),
    ("service", "2. SERVICE", [
        ("S1", "S1 — Accueil client", ""),
        ("S2", "S2 — Produit recommandé", ""),
        ("S3", "S3 — Prix annoncé avant", ""),
    ]),
    ("equipements", "3. ÉQUIPEMENTS", [
        ("E1", "E1 — Matériel de vidange OK", E1_AIDE),
        ("E2", "E2 — Outillage OK", E2_AIDE),
        ("E3", "E3 — Stockage rangé", ""),
    ]),
    ("affichage", "4. AFFICHAGE", [
        ("A1", "A1 — Prix affichés en baie", ""),
        ("A2", "A2 — PLV îlot visible", ""),
        ("A3", "A3 — Étiquettes prix shop", ""),
    ]),
    ("hsse", "5. HSSE", [
        ("H1", "H1 — EPI portés", ""),
        ("H2", "H2 — Déchets conformes", ""),
    ]),
    ("competences", "6. COMPÉTENCES", [
        ("C1", "C1 — Oil Specialist actif", ""),
        ("C2", "C2 — Produit adapté au véhicule", ""),
        ("C3", "C3 — Argumentaire produit", ""),
    ]),
]

BLOC_NOMS_COURTS = {
    "proprete": "Propreté", "service": "Service", "equipements": "Équipements",
    "affichage": "Affichage", "hsse": "HSSE", "competences": "Compétences",
}

TOUS_LES_POINTS = [c for c, _ in ELIMINATOIRES] + [c for _, _, items in BLOCS for c, _, _ in items]
LIBELLES = {c: l for c, l in ELIMINATOIRES}
LIBELLES.update({c: l for _, _, items in BLOCS for c, l, _ in items})

SEUIL_BLOC_DEFAUT = 0.70
SEUIL_GLOBAL_DEFAUT = 0.85

STATUTS = ("Critique", "À corriger", "Conforme")

# ---------------------------------------------------------------- Inventaire
STATUTS_RELEVE = (
    "Relevé", "Station non engagée LOS", "Station sans superviseur",
    "Non visitée", "En KDR", "Pas de baie",
)

# (clé, titre, besoin) — besoin : "baie" = visible si Baie = Oui,
# "shsc" = visible si Baie = Oui et SHSC = Oui.
EQUIPEMENTS = [
    ("bloc1", "Bloc 1 — MATÉRIEL DE VIDANGE", [
        ("fosse", "Fosse de vidange", "baie"),
        ("pont", "Pont / Plateforme de levage", "baie"),
        ("vid_aspiration", "Vidangeur par aspiration", "baie"),
        ("vid_gravite", "Vidangeur par gravité", "baie"),
        ("vid_mixte", "Vidangeur mixte", "baie"),
        ("pompe_graisse", "Pompe à graisse", "baie"),
        ("surpresseur", "Surpresseur / pompe à huile", "baie"),
        ("enrouleur_air", "Enrouleur d'air", "baie"),
        ("cric", "Cric rouleur", "baie"),
    ]),
    ("bloc2", "Bloc 2 — OUTILLAGE ESSENTIEL / ENTRETIEN RAPIDE", [
        ("diagnostic", "Outil diagnostic", "baie"),
        ("servante", "Servante d’atelier", "baie"),
        ("caisse_outils", "Caisse à outils", "baie"),
        ("coiffes", "Jeu de coiffes / \nCloches filtres à huile", "baie"),
        ("lampe", "Lampe d'inspection", "baie"),
        ("tournevis", "Jeu de tournevis", "baie"),
        ("cle_dynamo", "Clé dynamométrique", "baie"),
        ("controleur_pression", "Contrôleur de pression", "baie"),
        ("chandelle", "Kit chandelle", "baie"),
    ]),
    ("bloc3", "Bloc 3 — SHSC / SERVICE RAPIDE / SERVICES ADDITIONNELS", [
        ("enrouleur_comprime", "Enrouleur d’air comprimé", "baie"),
        ("demonte_pneu", "Démonte pneu tourisme", "shsc"),
        ("run_flat", "Kit run flat", "shsc"),
        ("presseur_ressorts", "Presseur de ressorts", "shsc"),
        ("equilibreuse", "Équilibreuse de roues", "shsc"),
        ("geometrie", "Appareil de géométrie / \nParallélisme", "shsc"),
        ("regle_phare", "Règle phare", "shsc"),
        ("charge_clim", "Charge clim", "shsc"),
        ("detection_fuite", "Kit détection de fuite", "shsc"),
        ("cle_chocs", "Clé à chocs", "shsc"),
        ("repousse_piston", "Repousse piston", "shsc"),
        ("testeur_batterie", "Testeur de batterie", "shsc"),
    ]),
]
TOUS_EQUIPEMENTS = [k for _, _, items in EQUIPEMENTS for k, _, _ in items]
# Équipements qui alimentent E1 / E2 (blocs 1 et 2).
EQUIPEMENTS_E1_E2 = [k for b, _, items in EQUIPEMENTS if b in ("bloc1", "bloc2") for k, _, _ in items]
EQUIPEMENT_LIBELLES = {k: l.replace(" \n", " ") for _, _, items in EQUIPEMENTS for k, l, _ in items}

# --------------------------------------------------------------------- Stock
STOCK_METHODES = (
    "Physique (comptage sur site)",
    "Système (communiqué par la station)",
    "Refus ou pas d'accès au stock",
    "Aucun inventaire réalisé",
)
STOCK_FREQUENCES = ("Hebdomadaire", "Mensuel", "Trimestriel", "Ponctuel", "Aucune")
STOCK_ECART_TOLERE = 0.05
