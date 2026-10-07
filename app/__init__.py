import datetime as dt
import os
import secrets
from urllib.parse import urlsplit

import click
from flask import Flask, abort, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import db, scoring


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or _instance_secret(app),
        DATABASE=os.environ.get("DATABASE_PATH") or os.path.join(app.instance_path, "los.sqlite3"),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=dt.timedelta(days=30),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)

    if os.environ.get("BEHIND_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()
        _bootstrap_admin()

    @app.before_request
    def _csrf_protect():
        if request.method == "POST" and not app.config.get("TESTING_NO_CSRF"):
            token = session.get("csrf")
            if not token or token != request.form.get("csrf"):
                abort(400, "Jeton de sécurité invalide — rechargez la page.")

    @app.after_request
    def _security_headers(resp):
        logo_host = urlsplit(os.environ.get("LOGO_URL", LOGO_URL_DEFAUT))
        h = resp.headers
        h.setdefault("Content-Security-Policy",
                     "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                     f"img-src 'self' data: {logo_host.scheme}://{logo_host.netloc}; "
                     "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        if app.config["SESSION_COOKIE_SECURE"]:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if resp.mimetype == "text/html":
            h["Cache-Control"] = "no-store"  # pas de pages privées dans le cache (PC partagé)
        return resp

    @app.context_processor
    def _inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        from .terrain import pending_count
        return {"csrf_token": session["csrf"], "pct": scoring.pct, "logo_url": _logo_url(app),
                "week_label": scoring.week_label, "month_label": scoring.month_label,
                "pending_count": pending_count}

    from .auth import bp as auth_bp, current_user
    from .terrain import bp as terrain_bp
    from .admin import bp as admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(terrain_bp)
    app.register_blueprint(admin_bp)
    app.jinja_env.globals["current_user"] = current_user

    _register_cli(app)
    return app


LOGO_URL_DEFAUT = "https://sc.atzer-ma.com/img/shell.svg"


def _logo_url(app):
    """Logo local (static/img/shell.svg) s'il existe, sinon LOGO_URL ou le logo en ligne."""
    if os.path.exists(os.path.join(app.static_folder, "img", "shell.svg")):
        return url_for("static", filename="img/shell.svg")
    return os.environ.get("LOGO_URL", LOGO_URL_DEFAUT)


def _bootstrap_admin():
    """Crée le premier admin depuis ADMIN_EMAIL / ADMIN_PASSWORD (hébergement sans terminal)."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if email and len(password) >= 8 and not db.query("SELECT 1 FROM users WHERE email = ?", (email,), one=True):
        db.execute("INSERT INTO users(email, name, role, password_hash) VALUES (?, 'Admin', 'admin', ?)",
                   (email, generate_password_hash(password)))


def _instance_secret(app):
    """Clé de session persistée dans instance/ si SECRET_KEY n'est pas fournie."""
    os.makedirs(app.instance_path, exist_ok=True)
    path = os.path.join(app.instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip()


def _register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Nom", default="Admin")
    @click.password_option()
    def create_admin(email, name, password):
        """Crée (ou réinitialise) un compte administrateur."""
        email = email.strip().lower()
        db.execute(
            "INSERT INTO users(email, name, role, password_hash) VALUES (?, ?, 'admin', ?) "
            "ON CONFLICT(email) DO UPDATE SET role='admin', active=1, password_hash=excluded.password_hash",
            (email, name, generate_password_hash(password)))
        click.echo(f"Administrateur prêt : {email}")

    @app.cli.command("import-fiche")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    @click.option("--stations-only", is_flag=True, help="N'importe que la liste des stations.")
    def import_fiche_cmd(path, stations_only):
        """Importe la fiche Excel (stations + inventaire, stock et checklist)."""
        from .importer import import_fiche
        with open(path, "rb") as f:
            report = import_fiche(f, with_data=not stations_only, user_id=None)
        for line in report:
            click.echo(line)
