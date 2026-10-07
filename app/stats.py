"""Agrégats du tableau de bord (web et Excel)."""
import datetime as dt
import json
from collections import defaultdict

from . import scoring
from .db import query, seuils
from .referentiel import BLOCS, ELIMINATOIRES, LIBELLES, TOUS_LES_POINTS


def filtered_stations(secteur=None, sup_id=None):
    sql = ("SELECT s.*, u.name AS sup_name FROM stations s LEFT JOIN users u ON u.id = s.supervisor_id "
           "WHERE s.active = 1")
    args = []
    if secteur:
        sql += " AND s.secteur = ?"
        args.append(secteur)
    if sup_id == "none":
        sql += " AND s.supervisor_id IS NULL"
    elif sup_id:
        sql += " AND s.supervisor_id = ?"
        args.append(int(sup_id))
    return query(sql + " ORDER BY s.secteur, s.sort_order, s.name", args)


def week_rows(week, stations):
    """[(station, checklist_row|None, data|None, score|None)] pour une semaine."""
    seuil_bloc, seuil_global = seuils()
    rows = {r["station_id"]: r for r in query("SELECT * FROM checklists WHERE week_start = ?", (week.isoformat(),))}
    out = []
    for s in stations:
        c = rows.get(s["id"])
        data = json.loads(c["data"]) if c else None
        sc = scoring.score_checklist(data.get("answers"), seuil_bloc, seuil_global) if data else None
        out.append((s, c, data, sc))
    return out


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def summarize(rows):
    sent = [(s, c, d, sc) for s, c, d, sc in rows if c and c["status"] == "envoye"]
    statuts = defaultdict(int)
    for *_, sc in sent:
        statuts[sc["statut"] or "—"] += 1
    return {
        "stations": len(rows),
        "envoyees": len(sent),
        "brouillons": sum(1 for _, c, _, _ in rows if c and c["status"] == "brouillon"),
        "completion": len(sent) / len(rows) if rows else None,
        "score": _avg(sc["global"] for *_, sc in sent),
        "critique": statuts["Critique"],
        "a_corriger": statuts["À corriger"],
        "conforme": statuts["Conforme"],
        "blocs": {cle: _avg(sc["blocs"][cle] for *_, sc in sent) for cle, _, _ in BLOCS},
    }


def dashboard(week, secteur=None, sup_id=None, trend_weeks=8):
    stations = filtered_stations(secteur, sup_id)
    rows = week_rows(week, stations)
    sent = [(s, c, d, sc) for s, c, d, sc in rows if c and c["status"] == "envoye"]

    by_secteur = defaultdict(list)
    by_sup = defaultdict(list)
    for r in rows:
        by_secteur[r[0]["secteur"]].append(r)
        by_sup[r[0]["sup_name"] or "— Non assigné —"].append(r)

    top_non = []
    for code in TOUS_LES_POINTS:
        answered = [d["answers"].get(code) for _, _, d, _ in sent if d["answers"].get(code) in ("Oui", "Non")]
        n = answered.count("Non")
        if n:
            top_non.append({"code": code, "libelle": LIBELLES[code], "non": n, "taux": n / len(answered)})
    top_non.sort(key=lambda x: (-x["non"], -x["taux"]))

    critiques = []
    for s, c, d, sc in sent:
        if sc["statut"] == "Critique":
            elims = [lib for code, lib in ELIMINATOIRES if d["answers"].get(code) == "Non"]
            critiques.append({"station": s, "elims": elims, "checklist": c})

    actions = []
    for s, c, d, sc in sent:
        for cle, titre, items in BLOCS:
            nons = [code for code, _, _ in items if d["answers"].get(code) == "Non"]
            if nons:
                actions.append({"station": s, "bloc": titre, "points": nons,
                                "constat": d["constats"].get(cle, ""), "action": d["actions"].get(cle, ""),
                                "responsable": d.get("responsable", "")})

    trend = []
    for i in range(trend_weeks - 1, -1, -1):
        w = week - dt.timedelta(days=7 * i)
        g = summarize(week_rows(w, stations)) if i else summarize(rows)
        trend.append({"week": w, **g})

    return {
        "week": week,
        "kpi": summarize(rows),
        "by_secteur": sorted(((k, summarize(v)) for k, v in by_secteur.items()), key=lambda x: x[0]),
        "by_sup": sorted(((k, summarize(v)) for k, v in by_sup.items()), key=lambda x: x[0]),
        "top_non": top_non[:10],
        "critiques": critiques,
        "non_faites": [s for s, c, _, _ in rows if not c or c["status"] != "envoye"],
        "actions": actions,
        "trend": trend,
        "rows": rows,
    }
