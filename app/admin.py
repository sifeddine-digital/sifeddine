"""Espace administrateur : tableau de bord, stations, superviseurs, import / export, journal, sauvegarde."""
import datetime as dt
import io
import json
import os
import secrets
import sqlite3
import tempfile

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request, send_file,
                   url_for)
from werkzeug.security import generate_password_hash

from . import scoring
from .auth import admin_required, current_user, start_session
from .db import execute, get_db, log, query, secteurs, seuils, set_setting
from .stats import dashboard as build_dashboard

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _supervisors():
    return query("SELECT * FROM users WHERE role = 'superviseur' ORDER BY active DESC, name")


@bp.route("/")
@admin_required
def dashboard():
    week = scoring.parse_week(request.args.get("w"))
    secteur = request.args.get("secteur") or None
    sup = request.args.get("sup") or None
    d = build_dashboard(week, secteur, sup)
    seuil_bloc, seuil_global = seuils()
    return render_template("admin/dashboard.html", d=d, week=week, secteur=secteur, sup=sup,
                           secteurs=secteurs(), sups=_supervisors(),
                           prev_week=week - dt.timedelta(days=7), next_week=week + dt.timedelta(days=7),
                           seuil_bloc=seuil_bloc, seuil_global=seuil_global)


# ----------------------------------------------------------------- stations
@bp.route("/stations", methods=["GET", "POST"])
@admin_required
def stations():
    if request.method == "POST":
        ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
        action = request.form.get("action")
        if not ids:
            flash("Cochez au moins une station.", "error")
        elif action == "assign":
            sup = request.form.get("supervisor_id")
            sup_id = int(sup) if sup and sup.isdigit() else None
            _bulk("UPDATE stations SET supervisor_id = ? WHERE id IN ({})", [sup_id], ids)
            name = query("SELECT name FROM users WHERE id = ?", (sup_id,), one=True) if sup_id else None
            log("affectation", f"{len(ids)} station(s) → {name['name'] if name else 'aucun superviseur'}")
            flash(f"{len(ids)} station(s) affectée(s).", "ok")
        elif action in ("activate", "deactivate"):
            _bulk("UPDATE stations SET active = ? WHERE id IN ({})", [1 if action == "activate" else 0], ids)
            log("stations " + ("activées" if action == "activate" else "désactivées"), f"{len(ids)} station(s)")
            flash(f"{len(ids)} station(s) mise(s) à jour.", "ok")
        return redirect(request.full_path)
    secteur, sup, q = request.args.get("secteur", ""), request.args.get("sup", ""), request.args.get("q", "").strip()
    sql = ("SELECT s.*, u.name AS sup_name FROM stations s LEFT JOIN users u ON u.id = s.supervisor_id WHERE 1=1")
    args = []
    if secteur:
        sql += " AND s.secteur = ?"
        args.append(secteur)
    if sup == "none":
        sql += " AND s.supervisor_id IS NULL"
    elif sup.isdigit():
        sql += " AND s.supervisor_id = ?"
        args.append(int(sup))
    if q:
        sql += " AND (s.name LIKE ? OR s.ship_to LIKE ? OR s.territoire LIKE ?)"
        args += [f"%{q}%"] * 3
    rows = query(sql + " ORDER BY s.secteur, s.sort_order, s.name", args)
    return render_template("admin/stations.html", rows=rows, secteurs=secteurs(), sups=_supervisors(),
                           secteur=secteur, sup=sup, q=q)


def _bulk(sql, head, ids):
    execute(sql.format(",".join("?" * len(ids))), head + ids)


@bp.route("/stations/new", methods=["GET", "POST"])
@bp.route("/stations/<int:station_id>", methods=["GET", "POST"])
@admin_required
def station_edit(station_id=None):
    st = query("SELECT * FROM stations WHERE id = ?", (station_id,), one=True) if station_id else None
    if station_id and st is None:
        abort(404)
    if request.method == "POST":
        f = request.form
        vals = (f.get("ship_to", "").strip(), f.get("name", "").strip(), f.get("secteur", "").strip(),
                f.get("territoire", "").strip(),
                int(f["supervisor_id"]) if f.get("supervisor_id", "").isdigit() else None,
                1 if f.get("active") else 0)
        if not all(vals[:3]):
            flash("Code Ship-to, nom et secteur sont obligatoires.", "error")
        else:
            try:
                if st:
                    execute("UPDATE stations SET ship_to=?, name=?, secteur=?, territoire=?, supervisor_id=?, "
                            "active=? WHERE id=?", vals + (st["id"],))
                else:
                    execute("INSERT INTO stations(ship_to, name, secteur, territoire, supervisor_id, active, "
                            "sort_order) VALUES (?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(sort_order),0)+1 "
                            "FROM stations))", vals)
                log("station modifiée" if st else "station créée", f"{vals[1]} ({vals[0]})")
                flash("Station enregistrée.", "ok")
                return redirect(url_for("admin.stations"))
            except sqlite3.IntegrityError:
                flash("Ce code Ship-to existe déjà.", "error")
    history = []
    if st:
        seuil_bloc, seuil_global = seuils()
        for c in query("SELECT * FROM checklists WHERE station_id = ? ORDER BY week_start DESC LIMIT 12", (st["id"],)):
            d = json.loads(c["data"])
            history.append((c, d, scoring.score_checklist(d.get("answers"), seuil_bloc, seuil_global)))
    return render_template("admin/station_edit.html", st=st, sups=_supervisors(), secteurs=secteurs(),
                           history=history)


@bp.route("/checklist/<int:checklist_id>/lock", methods=["POST"])
@admin_required
def checklist_lock(checklist_id):
    c = query("SELECT c.*, s.name FROM checklists c JOIN stations s ON s.id = c.station_id WHERE c.id = ?",
              (checklist_id,), one=True)
    if c is None:
        abort(404)
    if request.form.get("op") == "reopen":
        execute("UPDATE checklists SET status = 'brouillon', locked = 0 WHERE id = ?", (checklist_id,))
        log("checklist renvoyée pour correction", f"{c['name']} — {c['week_start']}")
        flash("Checklist rouverte : le superviseur peut la corriger et la renvoyer.", "ok")
    else:
        execute("UPDATE checklists SET locked = 1 - locked WHERE id = ?", (checklist_id,))
        log("checklist " + ("déverrouillée" if c["locked"] else "verrouillée"), f"{c['name']} — {c['week_start']}")
        flash("Verrou modifié.", "ok")
    return redirect(url_for("terrain.checklist", station_id=c["station_id"], week=c["week_start"]))


# -------------------------------------------------------------- superviseurs
@bp.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        f = request.form
        email = f.get("email", "").strip().lower()
        name = f.get("name", "").strip()
        password = f.get("password", "").strip() or _gen_password()
        role = "admin" if f.get("role") == "admin" else "superviseur"
        if not email or "@" not in email or not name:
            flash("Nom et email valides obligatoires.", "error")
        elif len(password) < 8:
            flash("Mot de passe : 8 caractères minimum.", "error")
        else:
            try:
                cur = execute("INSERT INTO users(email, name, phone, role, password_hash, must_change) "
                              "VALUES (?, ?, ?, ?, ?, 1)",
                              (email, name, f.get("phone", "").strip(), role, generate_password_hash(password)))
            except sqlite3.IntegrityError:
                flash("Cet email existe déjà.", "error")
                return redirect(url_for("admin.users"))
            if f.get("secteur"):
                execute("UPDATE stations SET supervisor_id = ? WHERE secteur = ? AND supervisor_id IS NULL",
                        (cur.lastrowid, f["secteur"]))
            log("compte créé", f"{name} <{email}> ({role})")
            _flash_credentials(email, password)
            return redirect(url_for("admin.user_edit", user_id=cur.lastrowid))
    week = scoring.week_start().isoformat()
    rows = query("""SELECT u.*,
            (SELECT COUNT(*) FROM stations s WHERE s.supervisor_id = u.id AND s.active = 1) AS n_stations,
            (SELECT COUNT(*) FROM checklists c JOIN stations s ON s.id = c.station_id
               WHERE s.supervisor_id = u.id AND s.active = 1 AND c.week_start = ? AND c.status = 'envoye') AS n_done,
            (SELECT GROUP_CONCAT(DISTINCT s.secteur) FROM stations s WHERE s.supervisor_id = u.id) AS secteurs
        FROM users u ORDER BY u.role, u.active DESC, u.name""", (week,))
    return render_template("admin/users.html", rows=rows, secteurs=secteurs())


def _gen_password():
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def _flash_credentials(email, password):
    link = request.host_url.rstrip("/") + url_for("auth.login")
    flash(f"Accès à transmettre au superviseur :\nLien : {link}\nEmail : {email}\nMot de passe provisoire : {password}\n"
          "(il choisira son propre mot de passe à la première connexion)", "credentials")


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    u = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if u is None:
        abort(404)
    if request.method == "POST":
        f = request.form
        op = f.get("op")
        if op == "profile":
            role = "admin" if f.get("role") == "admin" else "superviseur"
            active = 1 if f.get("active") else 0
            if u["id"] == current_user()["id"] and (role != "admin" or not active):
                flash("Vous ne pouvez pas retirer vos propres droits admin.", "error")
            else:
                try:
                    execute("UPDATE users SET name=?, email=?, phone=?, role=?, active=? WHERE id=?",
                            (f.get("name", "").strip() or u["name"], f.get("email", "").strip().lower() or u["email"],
                             f.get("phone", "").strip(), role, active, u["id"]))
                    log("compte modifié", f"{u['name']} — rôle {role}, {'actif' if active else 'désactivé'}")
                    flash("Profil enregistré.", "ok")
                except sqlite3.IntegrityError:
                    flash("Cet email existe déjà.", "error")
        elif op == "password":
            password = f.get("password", "").strip() or _gen_password()
            if len(password) < 8:
                flash("Mot de passe : 8 caractères minimum.", "error")
            else:
                # nouveau hash => toutes les sessions ouvertes de ce compte sont fermées
                execute("UPDATE users SET password_hash = ?, must_change = ? WHERE id = ?",
                        (generate_password_hash(password), 0 if u["id"] == current_user()["id"] else 1, u["id"]))
                log("mot de passe réinitialisé", u["name"])
                if u["id"] == current_user()["id"]:
                    start_session(query("SELECT * FROM users WHERE id = ?", (u["id"],), one=True), True)
                    flash("Votre mot de passe a été changé.", "ok")
                else:
                    _flash_credentials(u["email"], password)
        elif op == "stations":
            ids = [int(i) for i in f.getlist("ids") if i.isdigit()]
            db = get_db()
            db.execute("UPDATE stations SET supervisor_id = NULL WHERE supervisor_id = ?", (u["id"],))
            if ids:
                db.execute(f"UPDATE stations SET supervisor_id = ? WHERE id IN ({','.join('?' * len(ids))})",
                           [u["id"]] + ids)
            db.commit()
            log("affectation", f"{len(ids)} station(s) → {u['name']}")
            flash(f"{len(ids)} station(s) affectée(s) à {u['name']}.", "ok")
        return redirect(url_for("admin.user_edit", user_id=u["id"]))
    stations = query("SELECT s.*, x.name AS sup_name FROM stations s LEFT JOIN users x ON x.id = s.supervisor_id "
                     "ORDER BY s.secteur, s.sort_order, s.name")
    grouped = {}
    for s in stations:
        grouped.setdefault(s["secteur"], []).append(s)
    return render_template("admin/user_edit.html", u=u, grouped=grouped)


# ---------------------------------------------------------- import / export
@bp.route("/import", methods=["GET", "POST"])
@admin_required
def import_view():
    report = None
    if request.method == "POST":
        f = request.files.get("fiche")
        if not f or not f.filename.lower().endswith((".xlsx", ".xlsm")):
            flash("Choisissez un fichier Excel (.xlsx).", "error")
        else:
            from .importer import import_fiche
            try:
                report = import_fiche(f.stream, with_data=bool(request.form.get("with_data")),
                                      user_id=current_user()["id"])
                log("import fiche Excel", f.filename[:120])
                flash("Import terminé.", "ok")
            except Exception as exc:  # fichier illisible ou mise en page différente
                flash(f"Import impossible : {exc}", "error")
    return render_template("admin/import.html", report=report)


@bp.route("/export")
@admin_required
def export():
    weeks = [scoring.week_start() - dt.timedelta(days=7 * i) for i in range(0, 26)]
    return render_template("admin/export.html", weeks=weeks, secteurs=secteurs(), sups=_supervisors(),
                           n_stations=query("SELECT COUNT(*) AS n FROM stations WHERE active = 1", one=True)["n"])


@bp.route("/export/telecharger")
@admin_required
def export_download():
    from .export_xlsx import MODES, build_workbook
    a = request.args
    mode = a.get("mode") if a.get("mode") in MODES else "dernier"
    chosen = [s for s in a.getlist("secteurs") if s] or None
    sup = a.get("sup") or None
    if sup not in (None, "none") and not str(sup).isdigit():
        sup = None
    n_weeks = max(1, min(52, int(a.get("weeks") or 8))) if str(a.get("weeks") or "8").isdigit() else 8
    week = scoring.parse_week(a.get("week")) if a.get("week") else None
    w_from = scoring.parse_week(a.get("from")) if a.get("from") else None
    w_to = scoring.parse_week(a.get("to")) if a.get("to") else None
    wb = build_workbook(mode=mode, secteurs=chosen, sup=sup, week=week, week_from=w_from, week_to=w_to,
                        n_weeks=n_weeks)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    if mode == "semaine":
        iso = (week or scoring.week_start()).isocalendar()
        name = f"LOS_Checklist_S{iso[1]:02d}_{iso[0]}.xlsx"
    elif mode == "periode":
        name = f"LOS_Checklist_{(w_from or scoring.week_start()):%Y-%m-%d}_au_{(w_to or scoring.week_start()):%Y-%m-%d}.xlsx"
    else:
        name = f"LOS_Checklist_DernierEtat_{dt.date.today():%Y-%m-%d}.xlsx"
    log("export Excel", f"{MODES[mode]} — {', '.join(chosen) if chosen else 'tous secteurs'}")
    return send_file(buf, as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        try:
            b = float(request.form["seuil_bloc"].replace(",", ".")) / 100
            g = float(request.form["seuil_global"].replace(",", ".")) / 100
            assert 0 < b <= 1 and 0 < g <= 1
        except (KeyError, ValueError, AssertionError):
            flash("Seuils invalides (entre 1 et 100 %).", "error")
        else:
            set_setting("seuil_bloc", b)
            set_setting("seuil_global", g)
            _rescore()
            log("seuils modifiés", f"bloc {b:.0%}, global {g:.0%}")
            flash("Seuils enregistrés — statuts recalculés.", "ok")
        return redirect(url_for("admin.settings"))
    b, g = seuils()
    return render_template("admin/settings.html", seuil_bloc=b, seuil_global=g)


def _rescore():
    b, g = seuils()
    db = get_db()
    for c in db.execute("SELECT id, data FROM checklists").fetchall():
        sc = scoring.score_checklist(json.loads(c["data"]).get("answers"), b, g)
        db.execute("UPDATE checklists SET score_global = ?, statut = ? WHERE id = ?", (sc["global"], sc["statut"], c["id"]))
    db.commit()


# -------------------------------------------------------- journal / sauvegarde
@bp.route("/journal")
@admin_required
def journal():
    q = request.args.get("q", "").strip()
    sql = ("SELECT j.*, u.name, u.email FROM journal j LEFT JOIN users u ON u.id = j.user_id")
    args = []
    if q:
        sql += " WHERE j.action LIKE ? OR j.detail LIKE ? OR u.name LIKE ?"
        args = [f"%{q}%"] * 3
    rows = query(sql + " ORDER BY j.id DESC LIMIT 300", args)
    return render_template("admin/journal.html", rows=rows, q=q)


@bp.route("/sauvegarde")
@admin_required
def backup():
    """Copie cohérente de la base (API backup de SQLite), à garder sur une clé USB / un drive."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    try:
        dst = sqlite3.connect(path)
        get_db().backup(dst)
        dst.close()
        with open(path, "rb") as fh:
            data = io.BytesIO(fh.read())
    finally:
        os.remove(path)
    log("sauvegarde téléchargée")
    current_app.logger.info("Sauvegarde téléchargée par %s", current_user()["email"])
    return send_file(data, as_attachment=True, download_name=f"LOS_sauvegarde_{dt.datetime.now():%Y-%m-%d_%H%M}.sqlite3",
                     mimetype="application/octet-stream")
