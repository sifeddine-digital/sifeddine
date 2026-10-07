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


def latest_rows(stations, week_from=None, week_to=None):
    """Dernière checklist ENVOYÉE de chaque station sur la période (toutes semaines si week_from est None)."""
    seuil_bloc, seuil_global = seuils()
    sql, args = "SELECT * FROM checklists WHERE status = 'envoye'", []
    if week_from:
        sql += " AND week_start >= ?"
        args.append(week_from.isoformat())
    if week_to:
        sql += " AND week_start <= ?"
        args.append(week_to.isoformat())
    latest = {}
    for c in query(sql + " ORDER BY week_start", args):
        latest[c["station_id"]] = c
    out = []
    for s in stations:
        c = latest.get(s["id"])
        data = json.loads(c["data"]) if c else None
        sc = scoring.score_checklist(data.get("answers"), seuil_bloc, seuil_global) if data else None
        out.append((s, c, data, sc))
    return out


def weekly_compliance(stations, week, n=8):
    """Par superviseur : envoyées / stations pour chacune des n dernières semaines."""
    weeks = [week - dt.timedelta(days=7 * i) for i in range(n - 1, -1, -1)]
    keys = [w.isoformat() for w in weeks]
    sent = {(r["station_id"], r["week_start"]) for r in query(
        f"SELECT station_id, week_start FROM checklists WHERE status = 'envoye' AND week_start IN ({','.join('?' * len(keys))})",
        keys)}
    by_sup = defaultdict(list)
    for s in stations:
        by_sup[(s["supervisor_id"], s["sup_name"] or "— Non assigné —")].append(s)
    table = []
    for (sid, name), sts in sorted(by_sup.items(), key=lambda x: (x[0][0] is None, x[0][1])):
        cells = []
        for k in keys:
            done = sum(1 for s in sts if (s["id"], k) in sent)
            cells.append((done, len(sts)))
        table.append({"sup_id": sid, "name": name, "cells": cells})
    return weeks, table


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
        by_sup[(r[0]["sup_name"] or "— Non assigné —", r[0]["supervisor_id"])].append(r)

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

    # relance WhatsApp : stations encore à faire, par superviseur
    phones = {u["id"]: u for u in query("SELECT id, name, phone FROM users WHERE role = 'superviseur'")}
    pending = defaultdict(list)
    for s, c, _, _ in rows:
        if s["supervisor_id"] and (not c or c["status"] != "envoye"):
            pending[s["supervisor_id"]].append(s["name"])
    relances = {}
    for sid, names in pending.items():
        u = phones.get(sid)
        if not u:
            continue
        msg = (f"Bonjour {u['name'].split(' ')[0]}, rappel checklist LOS ({scoring.week_label(week)}) : "
               f"{len(names)} station(s) restante(s) : " + ", ".join(names) + ". Merci !")
        digits = "".join(ch for ch in (u["phone"] or "") if ch.isdigit())
        if digits.startswith("0"):
            digits = "212" + digits[1:]  # numéro marocain local -> international
        relances[sid] = {"n": len(names), "text": msg, "phone": digits}

    cweeks, ctable = weekly_compliance(stations, week)
    strips = {row["sup_id"]: list(zip(cweeks, row["cells"])) for row in ctable}
    sups = [{"name": name, "sid": sid, "g": summarize(v), "strip": strips.get(sid, []), "relance": relances.get(sid)}
            for (name, sid), v in by_sup.items()]
    sups.sort(key=lambda x: (x["sid"] is None, x["name"]))

    return {
        "sups": sups,
        "chart": trend_chart(trend),
        "compliance": (cweeks, ctable),
        "relances": relances,
        "week": week,
        "kpi": summarize(rows),
        "by_secteur": sorted(((k, summarize(v)) for k, v in by_secteur.items()), key=lambda x: x[0]),
        "by_sup": sorted(((k[0], k[1], summarize(v)) for k, v in by_sup.items()), key=lambda x: (x[1] is None, x[0])),
        "top_non": top_non[:10],
        "critiques": critiques,
        "non_faites": [s for s, c, _, _ in rows if not c or c["status"] != "envoye"],
        "actions": actions,
        "trend": trend,
        "rows": rows,
    }


def trend_chart(trend, width=640, height=220):
    """Géométrie SVG d'un graphique en lignes (2 séries en %, un seul axe 0–100 %)."""
    left, right, top, bottom = 40, 64, 14, 30
    pw, ph = width - left - right, height - top - bottom
    n = len(trend)
    xs = [left + (pw * i / (n - 1) if n > 1 else pw / 2) for i in range(n)]
    y = lambda v: top + ph * (1 - v)  # noqa: E731
    series = []
    for key, label, color in (("completion", "Complétion", "var(--series-1)"), ("score", "Score moyen", "var(--series-2)")):
        pts = [(x, y(t[key]), t[key]) for x, t in zip(xs, trend) if t[key] is not None]
        segs, cur = [], []
        for i, t in enumerate(trend):  # coupe la ligne là où il n'y a pas de donnée
            if t[key] is None:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(f"{xs[i]:.1f},{y(t[key]):.1f}")
        if cur:
            segs.append(cur)
        series.append({"key": key, "label": label, "color": color, "segments": [" ".join(sg) for sg in segs],
                       "last": pts[-1] if pts else None})
    # étiquettes de fin : écarter si elles se chevauchent
    lasts = [s_["last"] for s_ in series if s_["last"]]
    if len(lasts) == 2 and abs(lasts[0][1] - lasts[1][1]) < 14:
        hi, lo = sorted(range(2), key=lambda i: lasts[i][1])
        mid = (lasts[0][1] + lasts[1][1]) / 2
        for s_, dy in ((series[hi], -8), (series[lo], 8)):
            s_["label_y"] = mid + dy
    for s_ in series:
        if s_["last"] and "label_y" not in s_:
            s_["label_y"] = s_["last"][1]
    cols = []
    step = pw / (n - 1) if n > 1 else pw
    for x, t in zip(xs, trend):
        cols.append({"x": x - step / 2, "w": step, "cx": x, "week": t["week"], "completion": t["completion"],
                     "score": t["score"], "envoyees": t["envoyees"], "stations": t["stations"]})
    grid = [(top + ph * (1 - g), f"{int(g * 100)} %") for g in (0, .25, .5, .75, 1)]
    return {"w": width, "h": height, "left": left, "right": width - right, "top": top, "bottom": top + ph,
            "series": series, "cols": cols, "grid": grid}
