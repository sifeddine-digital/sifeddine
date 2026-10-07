import datetime as dt
import io
import re

import openpyxl
import pytest
from werkzeug.security import generate_password_hash

from app import create_app, scoring
from app.db import execute, query
from app.referentiel import TOUS_LES_POINTS


@pytest.fixture
def app(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "t.sqlite3"), "SECRET_KEY": "test"})
    with app.app_context():
        for email, role in (("admin@x.ma", "admin"), ("sup@x.ma", "superviseur"), ("autre@x.ma", "superviseur")):
            execute("INSERT INTO users(email, name, role, password_hash) VALUES (?, ?, ?, ?)",
                    (email, email.split("@")[0], role, generate_password_hash("Secret123")))
        sup = query("SELECT id FROM users WHERE email = 'sup@x.ma'", one=True)["id"]
        execute("INSERT INTO stations(ship_to, name, secteur, territoire, supervisor_id) "
                "VALUES ('1001', 'SHELL A', '01 - Casa Nord', 'REN/5', ?)", (sup,))
        execute("INSERT INTO stations(ship_to, name, secteur, territoire) VALUES ('1002', 'SHELL B', '02 - Casa Sud', 'REC/3')")
    return app


def login(client, email):
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf" value="([^"]+)"', page)[1]
    client.post("/login", data={"email": email, "password": "Secret123", "csrf": token})
    return token


def full_answers(**over):
    data = {f"r_{c}": "Oui" for c in TOUS_LES_POINTS}
    data.update({f"r_{k}": v for k, v in over.items()})
    return data


def test_scoring_matches_sheet_rules():
    ans = {c: "Oui" for c in TOUS_LES_POINTS}
    assert scoring.score_checklist(ans, .7, .85)["statut"] == "Conforme"
    ans["elim2"] = "Non"
    assert scoring.score_checklist(ans, .7, .85)["statut"] == "Critique"
    ans = {c: "Oui" for c in TOUS_LES_POINTS}
    ans.update(H1="Non", H2="N/A")  # bloc HSSE à 0 %
    sc = scoring.score_checklist(ans, .7, .85)
    assert sc["blocs"]["hsse"] == 0 and sc["statut"] == "À corriger"
    assert sc["global"] == pytest.approx(15 / 16)


def test_login_required_and_csrf(app):
    c = app.test_client()
    assert c.get("/semaine").status_code == 302
    assert c.post("/login", data={"email": "sup@x.ma", "password": "Secret123"}).status_code == 400


def test_supervisor_sees_only_assigned_and_cannot_reach_admin(app):
    c = app.test_client()
    login(c, "sup@x.ma")
    page = c.get("/semaine").get_data(as_text=True)
    assert "SHELL A" in page and "SHELL B" not in page
    with app.app_context():
        other = query("SELECT id FROM stations WHERE ship_to = '1002'", one=True)["id"]
    assert c.get(f"/checklist/{other}/{scoring.week_start()}").status_code == 403
    assert c.get("/admin/").status_code == 403


def test_send_checklist_requires_constat_when_non(app):
    c = app.test_client()
    token = login(c, "sup@x.ma")
    with app.app_context():
        sid = query("SELECT id FROM stations WHERE ship_to = '1001'", one=True)["id"]
    url = f"/checklist/{sid}/{scoring.week_start()}"
    form = full_answers(P1="Non") | {"csrf": token, "action": "envoyer", "visit_date": dt.date.today().isoformat()}
    r = c.post(url, data=form)
    assert "constat obligatoire" in r.get_data(as_text=True)
    form["constat_proprete"] = "Baie sale"
    assert c.post(url, data=form).status_code == 302
    with app.app_context():
        row = query("SELECT * FROM checklists WHERE station_id = ?", (sid,), one=True)
    assert row["status"] == "envoye" and row["statut"] == "À corriger"  # Propreté 2/3 < 70 %


def test_old_week_is_read_only_for_supervisor(app):
    c = app.test_client()
    token = login(c, "sup@x.ma")
    old = scoring.week_start() - dt.timedelta(days=21)
    r = c.post(f"/checklist/1/{old}", data=full_answers() | {"csrf": token, "action": "brouillon"})
    assert r.status_code == 403


def test_admin_assigns_stations_and_exports(app):
    c = app.test_client()
    token = login(c, "admin@x.ma")
    with app.app_context():
        autre = query("SELECT id FROM users WHERE email = 'autre@x.ma'", one=True)["id"]
    r = c.post(f"/admin/users/{autre}", data={"csrf": token, "op": "stations", "ids": ["1", "2"]})
    assert r.status_code == 302
    with app.app_context():
        assert {s["supervisor_id"] for s in query("SELECT supervisor_id FROM stations")} == {autre}
    c.post("/checklist/1/" + str(scoring.week_start()),
           data=full_answers(elim1="Non") | {"csrf": token, "action": "envoyer", "visit_date": "2026-01-05"})
    assert c.get("/admin/").status_code == 200
    r = c.post("/admin/export", data={"csrf": token, "week": str(scoring.week_start()), "weeks": "4"})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["Dashboard", "Checklist", "Invt_Eqmt", "Invt_Stck", "Historique", "Plan d'actions"]
    ck = wb["Checklist"]
    assert ck["D2"].value == "Station" and ck["AW2"].value == "Statut global"
    assert ck["F3"].value == "Non" and ck["AW3"].value.startswith("=IF(COUNTIF($F3:$H3")


def test_export_import_round_trip(app, tmp_path):
    c = app.test_client()
    token = login(c, "admin@x.ma")
    week = scoring.week_start()
    c.post(f"/checklist/1/{week}", data=full_answers(S2="Non") | {
        "csrf": token, "action": "envoyer", "visit_date": week.isoformat(), "constat_service": "Pas de conseil"})
    data = c.post("/admin/export", data={"csrf": token, "week": str(week), "weeks": "1"}).data
    app2 = create_app({"DATABASE": str(tmp_path / "t2.sqlite3"), "SECRET_KEY": "test"})
    with app2.app_context():
        from app.importer import import_fiche
        report = import_fiche(io.BytesIO(data))
        assert "2 lues" in report[0]
        row = query("SELECT * FROM checklists", one=True)
        assert row["week_start"] == week.isoformat() and row["statut"] == "À corriger"
