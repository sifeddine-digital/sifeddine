import functools
import time

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query

bp = Blueprint("auth", __name__)

_failed = {}  # ip -> [timestamps] : limite les tentatives de connexion


def current_user():
    if "user" not in g:
        uid = session.get("uid")
        g.user = query("SELECT * FROM users WHERE id = ? AND active = 1", (uid,), one=True) if uid else None
    return g.user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*a, **kw):
        if current_user()["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapped


def is_admin():
    u = current_user()
    return u is not None and u["role"] == "admin"


@bp.route("/")
def index():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for("admin.dashboard" if u["role"] == "admin" else "terrain.semaine"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
        now = time.time()
        recent = [t for t in _failed.get(ip, []) if now - t < 600]
        if len(recent) >= 10:
            flash("Trop de tentatives. Réessayez dans 10 minutes.", "error")
            return render_template("login.html"), 429
        email = request.form.get("email", "").strip().lower()
        user = query("SELECT * FROM users WHERE email = ? AND active = 1", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            _failed.pop(ip, None)
            csrf = session.get("csrf")
            session.clear()
            session["csrf"] = csrf
            session["uid"] = user["id"]
            session.permanent = bool(request.form.get("remember"))
            execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (user["id"],))
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("auth.index"))
        _failed[ip] = recent + [now]
        flash("Email ou mot de passe incorrect.", "error")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("uid", None)
    return redirect(url_for("auth.login"))


@bp.route("/compte", methods=["GET", "POST"])
@login_required
def compte():
    if request.method == "POST":
        u = current_user()
        old, new = request.form.get("old", ""), request.form.get("new", "")
        if not check_password_hash(u["password_hash"], old):
            flash("Mot de passe actuel incorrect.", "error")
        elif len(new) < 8:
            flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "error")
        elif new != request.form.get("confirm"):
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), u["id"]))
            flash("Mot de passe modifié.", "ok")
            return redirect(url_for("auth.index"))
    return render_template("compte.html")
