"""Écrans terrain (superviseurs, sur téléphone) — aussi utilisés par l'admin."""
import datetime as dt
import json

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import scoring
from .auth import current_user, is_admin, login_required
from .db import execute, log, query, secteurs, seuils
from .referentiel import (BLOCS, ELIMINATOIRES, EQUIPEMENTS, EQUIPEMENTS_E1_E2, REPONSES,
                          STATUTS_RELEVE, STOCK_FREQUENCES, STOCK_METHODES, TOUS_LES_POINTS)

bp = Blueprint("terrain", __name__)


# ------------------------------------------------------------------ helpers
def my_stations(secteur=None, sup=None):
    if is_admin():
        sql = ("SELECT s.*, u.name AS sup_name FROM stations s LEFT JOIN users u ON u.id = s.supervisor_id "
               "WHERE s.active = 1")
        args = []
        if secteur:
            sql += " AND s.secteur = ?"
            args.append(secteur)
        if sup == "none":
            sql += " AND s.supervisor_id IS NULL"
        elif sup and str(sup).isdigit():
            sql += " AND s.supervisor_id = ?"
            args.append(int(sup))
        return query(sql + " ORDER BY s.secteur, s.sort_order, s.name", args)
    return query("SELECT s.*, NULL AS sup_name FROM stations s WHERE s.active = 1 AND s.supervisor_id = ? "
                 "ORDER BY s.secteur, s.sort_order, s.name", (current_user()["id"],))


def checklists_by_week(weeks):
    """{(station_id, 'AAAA-MM-JJ'): ligne} pour une liste de lundis."""
    if not weeks:
        return {}
    keys = [w.isoformat() for w in weeks]
    rows = query("SELECT station_id, week_start, status, statut, score_global, visit_date FROM checklists "
                 f"WHERE week_start IN ({','.join('?' * len(keys))})", keys)
    return {(r["station_id"], r["week_start"]): r for r in rows}


def dot_state(c):
    if c is None:
        return "miss"
    if c["status"] != "envoye":
        return "draft"
    return {"Critique": "crit", "À corriger": "warn", "Conforme": "ok"}.get(c["statut"], "ok")


def pending_count():
    """Checklists à faire par le superviseur connecté : semaine en cours + semaine précédente non envoyées."""
    u = current_user()
    if u is None or u["role"] != "superviseur":
        return 0
    if "pending" not in g:
        cur = scoring.week_start()
        prev = cur - dt.timedelta(days=7)
        row = query("""SELECT COUNT(*) AS n,
                SUM(EXISTS(SELECT 1 FROM checklists c WHERE c.station_id = s.id AND c.week_start = ? AND c.status = 'envoye')) AS cur,
                SUM(EXISTS(SELECT 1 FROM checklists c WHERE c.station_id = s.id AND c.week_start = ? AND c.status = 'envoye')) AS prev
            FROM stations s WHERE s.active = 1 AND s.supervisor_id = ?""",
                    (cur.isoformat(), prev.isoformat(), u["id"]), one=True)
        n = row["n"] or 0
        g.pending = (n - (row["cur"] or 0)) + (n - (row["prev"] or 0))
    return g.pending


def get_station(station_id):
    st = query("SELECT * FROM stations WHERE id = ?", (station_id,), one=True)
    if st is None:
        abort(404)
    if not is_admin() and st["supervisor_id"] != current_user()["id"]:
        abort(403)
    return st


def week_editable(week, locked=False):
    """Superviseur : semaine en cours + semaine précédente, sauf si verrouillée."""
    if is_admin():
        return True
    return not locked and week >= scoring.week_start() - dt.timedelta(days=7)


def month_editable(month):
    if is_admin():
        return True
    cur = scoring.month_start()
    prev = (cur - dt.timedelta(days=1)).replace(day=1)
    return month >= prev


def latest_inventaire(station_id, before_month=None):
    sql = "SELECT * FROM inventaires WHERE station_id = ?"
    args = [station_id]
    if before_month:
        sql += " AND month <= ?"
        args.append(before_month)
    return query(sql + " ORDER BY month DESC LIMIT 1", args, one=True)


def equipements_dotes(inv):
    """(dotés, manquants) sur les blocs 1-2 de l'inventaire — alimente E1/E2."""
    if not inv or inv["baie"] != "Oui":
        return None, None
    items = json.loads(inv["items"] or "{}")
    vals = [items.get(k) for k in EQUIPEMENTS_E1_E2]
    return vals.count("Oui"), vals.count("Non")


# ------------------------------------------------------------- semaine
@bp.route("/semaine")
@login_required
def semaine():
    week = scoring.parse_week(request.args.get("w"))
    current = scoring.week_start()
    secteur, sup = request.args.get("secteur") or None, request.args.get("sup") or None
    stations = my_stations(secteur, sup)
    history_weeks = [week - dt.timedelta(days=7 * i) for i in range(4, 0, -1)]
    by_week = checklists_by_week(history_weeks + [week])
    items = []
    for s in stations:
        c = by_week.get((s["id"], week.isoformat()))
        dots = [(w, dot_state(by_week.get((s["id"], w.isoformat())))) for w in history_weeks]
        items.append((s, c, dots))
    done = sum(1 for _, c, _ in items if c and c["status"] == "envoye")
    # semaine précédente encore modifiable : on la rappelle tant qu'elle n'est pas complète
    late = []
    if week == current:
        prev = (current - dt.timedelta(days=7)).isoformat()
        late = [s for s, _, dots in items if dots[-1][1] in ("miss", "draft")]
        late = [(s, by_week.get((s["id"], prev))) for s in late]
    deadline = week + dt.timedelta(days=6)
    sups = query("SELECT id, name FROM users WHERE role = 'superviseur' AND active = 1 ORDER BY name") if is_admin() else []
    return render_template(
        "semaine.html", week=week, items=items, done=done, total=len(items), late=late,
        prev_week=week - dt.timedelta(days=7), next_week=week + dt.timedelta(days=7),
        is_current=week == current, deadline=deadline, days_left=(deadline - dt.date.today()).days,
        history_weeks=history_weeks, secteur=secteur, sup=sup, secteurs=secteurs() if is_admin() else [],
        sups=sups, editable_week=week_editable(week))


@bp.route("/checklist/<int:station_id>/<week>", methods=["GET", "POST"])
@login_required
def checklist(station_id, week):
    st = get_station(station_id)
    week = scoring.parse_week(week)
    row = query("SELECT * FROM checklists WHERE station_id = ? AND week_start = ?",
                (station_id, week.isoformat()), one=True)
    editable = week_editable(week, row["locked"] if row else False)
    seuil_bloc, seuil_global = seuils()

    if request.method == "POST":
        if not editable:
            abort(403)
        data, errors = _read_checklist_form(request.form)
        send = request.form.get("action") == "envoyer"
        if send:
            errors += _validate_send(data)
        if errors and send:
            for e in errors[:6]:
                flash(e, "error")
            return _render_checklist(st, week, data, row, editable)
        sc = scoring.score_checklist(data["answers"], seuil_bloc, seuil_global)
        status = "envoye" if send else (row["status"] if row else "brouillon")
        lat, lng = _float(request.form.get("lat")), _float(request.form.get("lng"))
        execute(
            """INSERT INTO checklists(station_id, week_start, visit_date, data, status, score_global, statut,
                   lat, lng, updated_by, updated_at, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), CASE WHEN ? THEN datetime('now') END)
               ON CONFLICT(station_id, week_start) DO UPDATE SET
                   visit_date = excluded.visit_date, data = excluded.data, status = excluded.status,
                   score_global = excluded.score_global, statut = excluded.statut,
                   lat = COALESCE(excluded.lat, checklists.lat), lng = COALESCE(excluded.lng, checklists.lng),
                   updated_by = excluded.updated_by, updated_at = excluded.updated_at,
                   submitted_at = COALESCE(excluded.submitted_at, checklists.submitted_at)""",
            (station_id, week.isoformat(), data["visit_date"] or None, json.dumps(data, ensure_ascii=False),
             status, sc["global"], sc["statut"], lat, lng, current_user()["id"], send))
        if send:
            log("checklist envoyée", f"{st['name']} — {scoring.week_label(week)} — {scoring.pct(sc['global'])} {sc['statut']}")
            flash(f"✔ {st['name']} envoyée — {scoring.pct(sc['global']) or '—'} · {sc['statut'] or '—'}", "ok")
            back = week if week >= scoring.week_start() else scoring.week_start()
            return redirect(url_for("terrain.semaine", w=back.isoformat()))
        flash("Brouillon enregistré.", "ok")
        return redirect(url_for("terrain.checklist", station_id=station_id, week=week.isoformat()))

    data = json.loads(row["data"]) if row else {}
    return _render_checklist(st, week, data, row, editable)


def _render_checklist(st, week, data, row, editable):
    prev = query("SELECT data, week_start FROM checklists WHERE station_id = ? AND week_start < ? "
                 "ORDER BY week_start DESC LIMIT 1", (st["id"], week.isoformat()), one=True)
    prev_data = json.loads(prev["data"]) if prev else None
    dotes, manquants = equipements_dotes(latest_inventaire(st["id"], scoring.month_start(week).isoformat()))
    seuil_bloc, seuil_global = seuils()
    return render_template(
        "checklist.html", st=st, week=week, data=data, row=row, editable=editable,
        blocs=BLOCS, elims=ELIMINATOIRES, reponses=REPONSES,
        prev=prev_data, prev_week=prev["week_start"] if prev else None,
        dotes=dotes, manquants=manquants, seuil_bloc=seuil_bloc, seuil_global=seuil_global,
        today=dt.date.today().isoformat())


def _read_checklist_form(form):
    answers = {}
    for code in TOUS_LES_POINTS:
        v = form.get(f"r_{code}", "")
        if v in REPONSES:
            answers[code] = v
    data = {
        "answers": answers,
        "constats": {cle: form.get(f"constat_{cle}", "").strip() for cle, _, _ in BLOCS},
        "actions": {cle: form.get(f"action_{cle}", "").strip() for cle, _, _ in BLOCS},
        "responsable": form.get("responsable", "").strip(),
        "commentaire": form.get("commentaire", "").strip(),
        "visit_date": form.get("visit_date", "").strip(),
    }
    errors = []
    if data["visit_date"]:
        try:
            dt.date.fromisoformat(data["visit_date"])
        except ValueError:
            data["visit_date"] = ""
            errors.append("Date de visite invalide.")
    return data, errors


def _validate_send(data):
    errors = []
    missing = [c for c in TOUS_LES_POINTS if c not in data["answers"]]
    if missing:
        errors.append(f"{len(missing)} point(s) sans réponse : {', '.join(missing[:8])}.")
    if not data["visit_date"]:
        errors.append("Indiquez la date de visite.")
    for cle, titre, items in BLOCS:
        if any(data["answers"].get(c) == "Non" for c, _, _ in items) and not data["constats"][cle]:
            errors.append(f"{titre} : constat obligatoire quand un point est « Non ».")
    return errors


def _float(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# ---------------------------------------------------------------- mois
@bp.route("/mois")
@login_required
def mois():
    month = scoring.parse_month(request.args.get("m"))
    stations = my_stations()
    inv = {r["station_id"]: r for r in query("SELECT station_id, statut, updated_at FROM inventaires WHERE month = ?",
                                             (month.isoformat(),))}
    stk = {r["station_id"]: r for r in query("SELECT station_id, fiable, updated_at FROM stocks WHERE month = ?",
                                             (month.isoformat(),))}
    items = [(s, inv.get(s["id"]), stk.get(s["id"])) for s in stations]
    prev_m = (month - dt.timedelta(days=1)).replace(day=1)
    next_m = (month + dt.timedelta(days=32)).replace(day=1)
    return render_template("mois.html", month=month, items=items, prev_m=prev_m, next_m=next_m,
                           n_inv=sum(1 for _, i, _ in items if i), n_stk=sum(1 for _, _, k in items if k))


@bp.route("/inventaire/<int:station_id>/<month>", methods=["GET", "POST"])
@login_required
def inventaire(station_id, month):
    st = get_station(station_id)
    month = scoring.parse_month(month)
    editable = month_editable(month)
    row = query("SELECT * FROM inventaires WHERE station_id = ? AND month = ?",
                (station_id, month.isoformat()), one=True)
    if request.method == "POST":
        if not editable:
            abort(403)
        statut = request.form.get("statut", "")
        baie = request.form.get("baie", "")
        shsc = request.form.get("shsc", "") if baie == "Oui" else ""
        items = {}
        for _, _, its in EQUIPEMENTS:
            for key, _, need in its:
                v = request.form.get(f"eq_{key}", "")
                if v in ("Oui", "Non") and baie == "Oui" and (need == "baie" or shsc == "Oui"):
                    items[key] = v
        execute("""INSERT INTO inventaires(station_id, month, statut, baie, shsc, items, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(station_id, month) DO UPDATE SET statut = excluded.statut, baie = excluded.baie,
                   shsc = excluded.shsc, items = excluded.items, updated_by = excluded.updated_by,
                   updated_at = excluded.updated_at""",
                (station_id, month.isoformat(), statut if statut in STATUTS_RELEVE else "",
                 baie if baie in ("Oui", "Non") else "", shsc if shsc in ("Oui", "Non") else "",
                 json.dumps(items), current_user()["id"]))
        flash("Inventaire équipements enregistré ✔", "ok")
        return redirect(url_for("terrain.mois", m=month.isoformat()))
    prefilled = False
    if row is None:
        row = latest_inventaire(station_id, month.isoformat())
        prefilled = row is not None
    items = json.loads(row["items"]) if row else {}
    return render_template("inventaire.html", st=st, month=month, row=row, items=items, prefilled=prefilled,
                           editable=editable, equipements=EQUIPEMENTS, statuts=STATUTS_RELEVE)


@bp.route("/stock/<int:station_id>/<month>", methods=["GET", "POST"])
@login_required
def stock(station_id, month):
    st = get_station(station_id)
    month = scoring.parse_month(month)
    editable = month_editable(month)
    row = query("SELECT * FROM stocks WHERE station_id = ? AND month = ?",
                (station_id, month.isoformat()), one=True)
    if request.method == "POST":
        if not editable:
            abort(403)
        f = request.form
        fiable, methode = f.get("fiable", ""), f.get("methode", "")
        commentaire = f.get("commentaire", "").strip()
        if not commentaire and (fiable == "Non" or methode.startswith(("Refus", "Aucun"))):
            flash("Commentaire obligatoire si « Non », « Refus » ou « Aucun inventaire ».", "error")
            return render_template("stock.html", st=st, month=month, row=dict(f), editable=editable,
                                   methodes=STOCK_METHODES, frequences=STOCK_FREQUENCES)
        execute("""INSERT INTO stocks(station_id, month, fiable, methode, date_inventaire, frequence,
                       stock_physique, stock_systeme, commentaire, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(station_id, month) DO UPDATE SET fiable = excluded.fiable,
                   methode = excluded.methode, date_inventaire = excluded.date_inventaire,
                   frequence = excluded.frequence, stock_physique = excluded.stock_physique,
                   stock_systeme = excluded.stock_systeme, commentaire = excluded.commentaire,
                   updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                (station_id, month.isoformat(), fiable if fiable in ("Oui", "Non") else "",
                 methode if methode in STOCK_METHODES else "", f.get("date_inventaire", ""),
                 f.get("frequence") if f.get("frequence") in STOCK_FREQUENCES else "",
                 _float(f.get("stock_physique")), _float(f.get("stock_systeme")), commentaire,
                 current_user()["id"]))
        flash("Stock enregistré ✔", "ok")
        return redirect(url_for("terrain.mois", m=month.isoformat()))
    return render_template("stock.html", st=st, month=month, row=row, editable=editable,
                           methodes=STOCK_METHODES, frequences=STOCK_FREQUENCES)
