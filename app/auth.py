import functools
import time

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query

bp = Blueprint("auth", __name__)

# Limitation des tentatives de connexion (par adresse IP et par email), en mémoire.
_failed = {}
MAX_ECHECS, FENETRE = 8, 900  # 8 échecs en 15 min => blocage temporaire


def _pw_tag(user):
    """Empreinte du mot de passe gardée en session : changer le mot de passe déconnecte les autres appareils."""
    return user["password_hash"][-16:]


def current_user():
    if "user" not in g:
        uid = session.get("uid")
        user = query("SELECT * FROM users WHERE id = ? AND active = 1", (uid,), one=True) if uid else None
        if user is not None and session.get("pw") != _pw_tag(user):
            session.pop("uid", None)
            user = None
        g.user = user
    return g.user


def start_session(user, remember):
    csrf = session.get("csrf")
    session.clear()
    session["csrf"] = csrf
    session["uid"] = user["id"]
    session["pw"] = _pw_tag(user)
    session.permanent = bool(remember)


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


@bp.before_app_request
def _force_password_change():
    """Mot de passe donné par l'admin => le superviseur choisit le sien à la première connexion."""
    u = current_user()
    if u is not None and u["must_change"] and request.endpoint not in ("auth.compte", "auth.logout", "static"):
        return redirect(url_for("auth.compte"))


def _blocked(*keys):
    now = time.time()
    for k in keys:
        _failed[k] = [t for t in _failed.get(k, []) if now - t < FENETRE]
    return any(len(_failed[k]) >= MAX_ECHECS for k in keys)


@bp.route("/")
def index():
    u = current_user()
    if u is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for("admin.dashboard" if u["role"] == "admin" else "terrain.semaine"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        keys = ("ip:" + (request.remote_addr or ""), "email:" + email)
        if _blocked(*keys):
            flash("Trop de tentatives. Réessayez dans 15 minutes.", "error")
            return render_template("login.html", hide_chrome=True), 429
        user = query("SELECT * FROM users WHERE email = ? AND active = 1", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            for k in keys:
                _failed.pop(k, None)
            start_session(user, request.form.get("remember"))
            execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (user["id"],))
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("auth.index"))
        for k in keys:
            _failed.setdefault(k, []).append(time.time())
        flash("Email ou mot de passe incorrect.", "error")
    # déjà connecté (ex. l'admin veut tester un compte superviseur) : on propose de continuer
    # ou de se connecter avec un autre compte, au lieu de rediriger d'office.
    return render_template("login.html", hide_chrome=True, connected=current_user())


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("uid", None)
    session.pop("pw", None)
    return redirect(url_for("auth.login"))


@bp.route("/compte", methods=["GET", "POST"])
@login_required
def compte():
    u = current_user()
    if request.method == "POST":
        old, new = request.form.get("old", ""), request.form.get("new", "")
        if not check_password_hash(u["password_hash"], old):
            flash("Mot de passe actuel incorrect.", "error")
        elif len(new) < 8:
            flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "error")
        elif new == old:
            flash("Choisissez un mot de passe différent de l'actuel.", "error")
        elif new != request.form.get("confirm"):
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            execute("UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
                    (generate_password_hash(new), u["id"]))
            user = query("SELECT * FROM users WHERE id = ?", (u["id"],), one=True)
            start_session(user, session.permanent)
            flash("Mot de passe enregistré ✔", "ok")
            return redirect(url_for("auth.index"))
    return render_template("compte.html", must_change=bool(u["must_change"]))
