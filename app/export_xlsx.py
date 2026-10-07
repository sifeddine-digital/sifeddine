"""Export Excel : même mise en page que la fiche « LOS Inventaire & Checklist LS »
(onglets Checklist, Invt_Eqmt, Invt_Stck) + Dashboard, Historique et Plan d'actions."""
import datetime as dt
import json

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

from . import scoring
from .db import query, seuils
from .referentiel import (BLOC_NOMS_COURTS, BLOCS, E1_AIDE, E2_AIDE, ELIMINATOIRES, EQUIPEMENTS,
                          EQUIPEMENT_LIBELLES, LIBELLES, STATUTS_RELEVE, STOCK_FREQUENCES,
                          STOCK_METHODES, TOUS_LES_POINTS)
from .stats import filtered_stations, summarize, week_rows

FONT = "Urbanist SemiBold"
THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

RED_FILL, RED_FONT = "FFFFC7CE", "FF9C0006"
GREEN_FILL, GREEN_FONT = "FFC6EFCE", "FF006100"
STATUT_COLORS = {"Critique": "FFFF0000", "À corriger": "FFFFC000", "Conforme": "FF00B050"}


def fill(rgb):
    return PatternFill("solid", fgColor=rgb)


def font(bold=False, color="FF000000", size=10):
    return Font(name=FONT, bold=bold, color=color, size=size)


def style(cell, *, bold=False, color="FF000000", bg=None, size=10, align=CENTER, border=True, fmt=None):
    cell.font = font(bold, color, size)
    cell.alignment = align
    if bg:
        cell.fill = fill(bg)
    if border:
        cell.border = BORDER
    if fmt:
        cell.number_format = fmt
    return cell


def yes_no_cf(ws, rng, with_na=False):
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"Non"'], fill=fill(RED_FILL),
                                                  font=Font(color=RED_FONT)))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"Oui"'], fill=fill(GREEN_FILL),
                                                  font=Font(color=GREEN_FONT)))


def ship_value(s):
    return int(s) if str(s).isdigit() else s


# =================================================================== builder
def build_workbook(week, secteurs, n_weeks=8):
    stations = [s for s in filtered_stations() if s["secteur"] in secteurs]
    rows = week_rows(week, stations)
    month = scoring.month_start(week)
    seuil_bloc, seuil_global = seuils()

    wb = Workbook()
    dash = wb.active
    dash.title = "Dashboard"
    eq_last = _sheet_inventaire(wb.create_sheet("Invt_Eqmt"), stations, month)
    ck_last = _sheet_checklist(wb.create_sheet("Checklist", 1), rows, eq_last, seuil_bloc, seuil_global)
    _sheet_stock(wb.create_sheet("Invt_Stck"), stations, month)
    trend = _sheet_historique(wb.create_sheet("Historique"), stations, week, n_weeks, seuil_bloc, seuil_global)
    _sheet_actions(wb.create_sheet("Plan d'actions"), rows)
    _sheet_dashboard(dash, week, secteurs, rows, trend, ck_last, eq_last, len(stations))

    wb.properties.title = f"LOS Checklist — {scoring.week_label(week)}"
    wb.properties.creator = "LOS Checklist"
    for ws in wb.worksheets:
        ws.sheet_view.zoomScale = 90
    return wb


# ================================================================ Checklist
def _checklist_columns():
    """Liste ordonnée (type, clé, libellé) des colonnes A → AY de l'onglet Checklist."""
    cols = [("id", "secteur", "Secteur"), ("id", "territoire", "Territoire"), ("id", "ship", "Code Ship-to"),
            ("id", "name", "Station"), ("id", "date", "Date de visite")]
    cols += [("ans", code, lib) for code, lib in ELIMINATOIRES]
    for cle, _titre, items in BLOCS:
        nom = BLOC_NOMS_COURTS[cle]
        cols += [("ans", code, lib) for code, lib, _ in items]
        if cle == "equipements":
            cols += [("dotes", cle, "Équipements dotés"), ("manquants", cle, "Équipements manquants")]
        cols += [("constat", cle, f"Constat {nom}"), ("action", cle, f"Action {nom}"), ("pct", cle, f"% {nom}")]
    cols += [("nb_oui", "", "Nb Oui"), ("nb_non", "", "Nb Non"), ("global", "", "% global"),
             ("statut", "", "Statut global"), ("resp", "", "Responsable / Échéance"), ("com", "", "Commentaire")]
    return cols


CHECKLIST_WIDTHS = {"A": 28.4, "B": 17.4, "C": 12, "D": 29.2, "E": 16.1, "F": 14, "G": 11, "L": 28.6, "N": 11.9,
                    "O": 11, "R": 28.6, "T": 11.9, "U": 11, "X": 13.3, "Z": 28.6, "AB": 11.9, "AC": 11, "AF": 28.6,
                    "AH": 11.9, "AI": 11, "AK": 28.6, "AM": 11.9, "AN": 11, "AQ": 28.6, "AS": 11.9, "AT": 9.1,
                    "AV": 11.9, "AW": 18.1, "AX": 28.6, "AY": 40}


def _sheet_checklist(ws, rows, eq_last, seuil_bloc, seuil_global):
    cols = _checklist_columns()
    idx = {(t, k): i + 1 for i, (t, k, _) in enumerate(cols)}
    first, last = 3, max(3, 2 + len(rows))
    p_bloc, p_global = last + 4, last + 5  # cellules B des paramètres de scoring

    # --- ligne 1 : groupes
    groups = [("Identification station", "secteur", "date", "FFBFBFBF", "FF000000"),
              ("POINTS ÉLIMINATOIRES", ELIMINATOIRES[0][0], ELIMINATOIRES[-1][0], "FFFF0000", "FFFFFFFF")]
    for cle, titre, items in BLOCS:
        groups.append((titre, items[0][0], ("pct", cle), "FFBFBFBF", "FF000000"))
    groups.append(("SYNTHÈSE (automatique)", ("nb_oui", ""), ("com", ""), "FF1F4E79", "FFFFFFFF"))

    def col_of(k):
        if isinstance(k, tuple):
            return idx[k]
        return next(i for (t, kk), i in idx.items() if kk == k and t in ("id", "ans"))
    for title, a, b, bg, fg in groups:
        c1, c2 = col_of(a), col_of(b)
        ws.merge_cells(start_row=1, start_column=c1, end_row=1, end_column=c2)
        style(ws.cell(1, c1, title), bold=True, bg=bg, color=fg, size=11)
        for c in range(c1, c2 + 1):
            ws.cell(1, c).fill = fill(bg)
            ws.cell(1, c).border = BORDER
    ws.row_dimensions[1].height = 26.1

    # --- ligne 2 : en-têtes
    for i, (t, k, lib) in enumerate(cols, 1):
        bg = "FFFFD9D9" if t == "ans" and k.startswith("elim") else "FFDDEBF7" if t in ("dotes", "manquants") else "FFD9D9D9"
        style(ws.cell(2, i, lib), bold=True, bg=bg)
    ws.row_dimensions[2].height = 80.1

    # --- données
    eq_rng = f"Invt_Eqmt!$H$4:$Y${eq_last}"
    eq_key = f"Invt_Eqmt!$C$4:$C${eq_last}"
    ans_letters = {k: L(i) for (t, k), i in idx.items() if t == "ans"}
    for r, (s, c, d, _sc) in enumerate(rows, first):
        sent = c is not None and c["status"] == "envoye"
        d = d if sent else None
        for i, (t, k, _) in enumerate(cols, 1):
            cell = ws.cell(r, i)
            col = L(i)
            if t == "id":
                cell.value = {"secteur": s["secteur"], "territoire": s["territoire"], "ship": ship_value(s["ship_to"]),
                              "name": s["name"], "date": _d(d["visit_date"]) if d and d.get("visit_date") else None}[k]
                style(cell, fmt="dd/mm/yyyy" if k == "date" else None, align=LEFT if k == "name" else CENTER)
            elif t == "ans":
                cell.value = d["answers"].get(k) if d else None
                style(cell)
            elif t in ("constat", "action"):
                cell.value = (d["constats" if t == "constat" else "actions"].get(k) or None) if d else None
                style(cell, align=LEFT)
            elif t == "pct":
                items = [code for cle, _, its in BLOCS if cle == k for code, _, _ in its]
                a, b = ans_letters[items[0]], ans_letters[items[-1]]
                rng = f"{a}{r}:{b}{r}"
                cell.value = f'=IFERROR(COUNTIF({rng},"Oui")/(COUNTIF({rng},"Oui")+COUNTIF({rng},"Non")),"")'
                style(cell, bold=True, fmt="0%")
            elif t in ("dotes", "manquants"):
                word = "Oui" if t == "dotes" else "Non"
                look = f"INDEX({eq_rng},MATCH($C{r},{eq_key},0),0)"
                cell.value = f'=IFERROR(IF(COUNTA({look})=0,"",COUNTIF({look},"{word}")),"hors réf.")'
                style(cell)
            elif t in ("nb_oui", "nb_non"):
                word = "Oui" if t == "nb_oui" else "Non"
                parts = []
                for cle, _, its in BLOCS:
                    parts.append(f'COUNTIF({ans_letters[its[0][0]]}{r}:{ans_letters[its[-1][0]]}{r},"{word}")')
                cell.value = "=" + "+".join(parts)
                style(cell)
            elif t == "global":
                o, n = L(idx[("nb_oui", "")]), L(idx[("nb_non", "")])
                cell.value = f'=IFERROR({o}{r}/({o}{r}+{n}{r}),"")'
                style(cell, bold=True, fmt="0%")
            elif t == "statut":
                e1, e2 = ans_letters[ELIMINATOIRES[0][0]], ans_letters[ELIMINATOIRES[-1][0]]
                g = L(idx[("global", "")])
                pcts = ",".join(f"${L(idx[('pct', cle)])}{r}" for cle, _, _ in BLOCS)
                cell.value = (f'=IF(COUNTIF(${e1}{r}:${e2}{r},"Non")>0,"Critique",IF(${g}{r}="","",'
                              f'IF(OR(${g}{r}<$B${p_global},MIN({pcts})<$B${p_bloc}),"À corriger","Conforme")))')
                style(cell, bold=True)
            elif t == "resp":
                cell.value = (d.get("responsable") or None) if d else None
                style(cell, align=LEFT)
            elif t == "com":
                cell.value = (d.get("commentaire") or None) if d else None
                style(cell, align=LEFT)

    # --- mise en forme conditionnelle + listes déroulantes (comme la fiche)
    ans_ranges = []
    for cle, _, its in [("elim", "", [(c, "", "") for c, _ in ELIMINATOIRES])] + BLOCS:
        a, b = ans_letters[its[0][0]], ans_letters[its[-1][0]]
        ans_ranges.append(f"{a}{first}:{b}{last}")
    for rng in ans_ranges:
        yes_no_cf(ws, rng)
    dv = DataValidation(type="list", formula1='"Oui,Non,N/A"', allow_blank=True)
    for rng in ans_ranges:
        dv.add(rng)
    ws.add_data_validation(dv)
    for cle, _, _ in BLOCS:
        c = L(idx[("pct", cle)])
        _pct_cf(ws, f"{c}{first}:{c}{last}", c, first, f"$B${p_bloc}")
    g = L(idx[("global", "")])
    _pct_cf(ws, f"{g}{first}:{g}{last}", g, first, f"$B${p_global}")
    st = L(idx[("statut", "")])
    for label, rgb in STATUT_COLORS.items():
        ws.conditional_formatting.add(f"{st}{first}:{st}{last}", CellIsRule(
            operator="equal", formula=[f'"{label}"'], fill=fill(rgb), font=Font(color="FFFFFFFF", bold=True)))

    # --- paramètres + référentiel (sous le tableau, comme la fiche)
    ws.cell(last + 3, 1, "PARAMÈTRES DE SCORING (modifiables)").font = font(True)
    ws.cell(p_bloc, 1, "Seuil minimum par bloc").font = font()
    ws.cell(p_global, 1, "Seuil minimum global").font = font()
    for r, v in ((p_bloc, seuil_bloc), (p_global, seuil_global)):
        style(ws.cell(r, 2, v), bg="FFFFFF00", color="FF0000FF", fmt="0%")
    r = last + 8
    ref = [
        ("RÉFÉRENTIEL ÉQUIPEMENTS — comment distinguer E1 de E2 (source : onglet « Invt_Eqmt », blocs 1 et 2)", "bold_bg"),
        ("E1 — MATÉRIEL DE VIDANGE (équipement de baie : son indisponibilité arrête ou dégrade fortement le service)", "title"),
        (E1_AIDE, "note"),
        ("E2 — OUTILLAGE ESSENTIEL (outils à main et diagnostic : leur absence dégrade la qualité et la conformité de "
         "l'intervention, sans l'arrêter)", "title"),
        (E2_AIDE, "note"),
        ("ÉQUIPEMENTS SHSC (Bloc 3 de l'inventaire) : hors périmètre de la visite lubes, ils n'entrent ni dans E1 ni "
         "dans E2 et ne pèsent pas sur le score.", "plain"),
    ]
    for text, kind in ref:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, text)
        c.alignment = Alignment(wrap_text=True, vertical="center")
        if kind == "bold_bg":
            c.font, c.fill = font(True), fill("FFBFBFBF")
        elif kind == "title":
            c.font = font(True, "FF1F4E79")
        elif kind == "note":
            c.font = font(False, "FF808080")
        else:
            c.font = font()
        ws.row_dimensions[r].height = 45 if kind in ("note", "title") else 18
        r += 2 if kind == "note" else 1

    for col, w in CHECKLIST_WIDTHS.items():
        ws.column_dimensions[col].width = w
    for i in range(1, len(cols) + 1):
        if L(i) not in CHECKLIST_WIDTHS:
            ws.column_dimensions[L(i)].width = 11
    ws.freeze_panes = "E3"
    ws.auto_filter.ref = f"A2:{L(len(cols))}{last}"
    return last


def _pct_cf(ws, rng, col, first, threshold):
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND({col}{first}<>"",{col}{first}<{threshold})'],
                                                   fill=fill(RED_FILL)))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND({col}{first}<>"",{col}{first}>={threshold})'],
                                                   fill=fill(GREEN_FILL)))


def _d(s):
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# =============================================================== Invt_Eqmt
def _sheet_inventaire(ws, stations, month):
    inv = {r["station_id"]: r for r in query("SELECT * FROM inventaires WHERE month = ?", (month.isoformat(),))}
    style(ws.cell(1, 1, "Mois concerné :"), bold=True, border=False, align=LEFT)
    style(ws.cell(1, 2, month), bold=True, bg="FFFFFF00", fmt="mmm-yy", border=False, align=LEFT)
    style(ws.cell(2, 1, "Saisie mensuelle — la colonne « Statut relevé » explique les stations non relevées."),
          color="FF666666", border=False, align=Alignment(horizontal="left"))
    for c, t in ((5, "SUIVI"), (6, "PRÉREQUIS"), (7, "TYPE")):
        style(ws.cell(2, c, t), bold=True, bg="FF404040", color="FFFFFFFF")
    col = 8
    for (bloc, titre, items), bg in zip(EQUIPEMENTS, ("FF1F4E79", "FF2E75B6", "FF7F7F7F")):
        ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + len(items) - 1)
        style(ws.cell(2, col, titre), bold=True, bg=bg, color="FFFFFFFF")
        for c in range(col, col + len(items)):
            ws.cell(2, c).fill = fill(bg)
        col += len(items)
    headers = ["Secteur", "Territoire", "Code Ship-to", "Station", "Statut relevé", "Baie ?", "SHSC ?"]
    headers += [label for _, _, items in EQUIPEMENTS for _, label, _ in items]
    for i, h in enumerate(headers, 1):
        style(ws.cell(3, i, h), bold=True, color="FFFFFFFF", bg="FF404040" if i <= 5 else "FF1F4E23")
    ws.row_dimensions[3].height = 39.6
    keys = [k for _, _, items in EQUIPEMENTS for k, _, _ in items]
    first, last = 4, max(4, 3 + len(stations))
    for r, s in enumerate(stations, first):
        row = inv.get(s["id"])
        items = json.loads(row["items"]) if row else {}
        vals = [s["secteur"], s["territoire"], ship_value(s["ship_to"]), s["name"],
                row["statut"] if row else None, row["baie"] if row else None, row["shsc"] if row else None]
        vals += [items.get(k) for k in keys]
        for i, v in enumerate(vals, 1):
            c = ws.cell(r, i, v or None)
            style(c, color="FF404040" if i <= 5 else "FF000000", bg="FFFFF2CC" if i >= 8 else None,
                  align=LEFT if i == 4 else CENTER)
    end = L(len(headers))
    ws.conditional_formatting.add(f"A{first}:{end}{last}", FormulaRule(
        formula=[f'AND($E{first}<>"",$E{first}<>"Relevé")'], fill=fill("FFE7E6E6"), font=Font(color="FF7F7F7F")))
    yes_no_cf(ws, f"F{first}:{end}{last}")
    ws.conditional_formatting.add(f"G{first}:{end}{last}", FormulaRule(
        formula=[f'$F{first}="Non"'], fill=fill("FFBFBFBF"), font=Font(color="FF808080")))
    ws.conditional_formatting.add(f"AA{first}:{end}{last}", FormulaRule(
        formula=[f'$G{first}="Non"'], fill=fill("FFD9D9D9"), font=Font(color="FFBFBFBF")))
    dv = DataValidation(type="list", formula1='"Oui,Non"', allow_blank=True)
    dv.add(f"F{first}:{end}{last}")
    ws.add_data_validation(dv)
    dv2 = DataValidation(type="list", formula1='"' + ",".join(STATUTS_RELEVE) + '"', allow_blank=True)
    dv2.add(f"E{first}:E{last}")
    ws.add_data_validation(dv2)
    widths = [29.3, 21.1, 17.7, 34.6, 24.4, 11.4, 12.6]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[L(i)].width = w
    for i in range(8, len(headers) + 1):
        ws.column_dimensions[L(i)].width = 14
    ws.freeze_panes = "E4"
    ws.auto_filter.ref = f"A3:{end}{last}"
    return last


# =============================================================== Invt_Stck
def _sheet_stock(ws, stations, month):
    stk = {r["station_id"]: r for r in query("SELECT * FROM stocks WHERE month = ?", (month.isoformat(),))}
    style(ws.cell(1, 1, "Mois concerné :"), bold=True, border=False, align=LEFT)
    style(ws.cell(1, 2, month), bold=True, bg="FFFFFF00", fmt="mmm-yy", border=False, align=LEFT)
    style(ws.cell(2, 1, "Critère : « Stock fiable = Oui » signifie que le stock physique constaté correspond au stock "
                        "système (écart toléré ≤ 5 %). Saisir les deux volumes en colonnes I et J : l'écart se calcule "
                        "tout seul. Commentaire obligatoire si « Non », « Refus » ou « Aucun inventaire »."),
          color="FF666666", border=False, align=Alignment(horizontal="left"))
    headers = ["Secteur", "Territoire", "Code Ship-to", "Station", "Stock fiable ? (Oui/Non)", "Méthode d'obtention",
               "Date du dernier inventaire", "Fréquence d'inventaire", "Stock physique (L)",
               "Stock système station (L)", "Écart %", "Commentaire"]
    for i, h in enumerate(headers, 1):
        style(ws.cell(3, i, h), bold=True, color="FFFFFFFF", bg="FF1F4E23")
    ws.row_dimensions[3].height = 42
    first, last = 4, max(4, 3 + len(stations))
    for r, s in enumerate(stations, first):
        k = stk.get(s["id"])
        vals = [s["secteur"], s["territoire"], ship_value(s["ship_to"]), s["name"],
                k["fiable"] if k else None, k["methode"] if k else None,
                _d(k["date_inventaire"]) if k else None, k["frequence"] if k else None,
                k["stock_physique"] if k else None, k["stock_systeme"] if k else None,
                f'=IF(OR(I{r}="",J{r}="",J{r}=0),"",(I{r}-J{r})/J{r})', k["commentaire"] if k else None]
        for i, v in enumerate(vals, 1):
            c = ws.cell(r, i, v if v != "" else None)
            style(c, bg="FFFFF2CC" if i in (7, 9, 10) else None, align=LEFT if i in (4, 6, 12) else CENTER,
                  fmt="dd/mm/yyyy" if i == 7 else "#,##0" if i in (9, 10) else "0.0%" if i == 11 else None)
    ws.conditional_formatting.add(f"A{first}:L{last}", FormulaRule(formula=[f'$E{first}="Oui"'], fill=fill("FFE2EFDA")))
    ws.conditional_formatting.add(f"A{first}:L{last}", FormulaRule(formula=[f'$E{first}="Non"'], fill=fill("FFFCE4E4")))
    ws.conditional_formatting.add(f"K{first}:K{last}", FormulaRule(
        formula=[f'AND(K{first}<>"",ABS(K{first})>0.05)'], fill=fill(RED_FILL), font=Font(color=RED_FONT, bold=True)))
    ws.conditional_formatting.add(f"L{first}:L{last}", FormulaRule(
        formula=[f'AND($L{first}="",OR($E{first}="Non",LEFT($F{first},5)="Refus",LEFT($F{first},5)="Aucun"))'],
        fill=fill(RED_FILL)))
    for rng, opts in ((f"E{first}:E{last}", ("Oui", "Non")), (f"F{first}:F{last}", STOCK_METHODES),
                      (f"H{first}:H{last}", STOCK_FREQUENCES)):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        dv.add(rng)
        ws.add_data_validation(dv)
    for col, w in zip("ABCDEFGHIJKL", (29.9, 19.9, 12.1, 32.7, 16.1, 33.4, 13, 14.3, 14.3, 14.3, 10, 90)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "E4"
    ws.auto_filter.ref = f"A3:L{last}"


# ============================================================== Historique
def _sheet_historique(ws, stations, week, n_weeks, seuil_bloc, seuil_global):
    headers = ["Semaine", "Lundi", "Secteur", "Territoire", "Code Ship-to", "Station", "Superviseur", "État",
               "Date de visite"] + [f"% {BLOC_NOMS_COURTS[c]}" for c, _, _ in BLOCS] + \
              ["Nb Oui", "Nb Non", "% global", "Statut global"]
    for i, h in enumerate(headers, 1):
        style(ws.cell(1, i, h), bold=True, color="FFFFFFFF", bg="FF1F4E79")
    ws.row_dimensions[1].height = 32
    r = 2
    trend = []
    for i in range(n_weeks - 1, -1, -1):
        w = week - dt.timedelta(days=7 * i)
        rows = week_rows(w, stations)
        trend.append((w, summarize(rows)))
        iso = w.isocalendar()
        for s, c, d, sc in rows:
            etat = "Non faite" if c is None else "Envoyée" if c["status"] == "envoye" else "Brouillon"
            vals = [f"S{iso[1]:02d}-{iso[0]}", w, s["secteur"], s["territoire"], ship_value(s["ship_to"]), s["name"],
                    s["sup_name"] or "", etat, _d(d.get("visit_date")) if d else None]
            vals += [sc["blocs"][cle] if sc else None for cle, _, _ in BLOCS]
            vals += [sc["oui"] if sc else None, sc["non"] if sc else None, sc["global"] if sc else None,
                     sc["statut"] if sc else None]
            for j, v in enumerate(vals, 1):
                fmt = "dd/mm/yyyy" if j in (2, 9) else "0%" if 10 <= j <= 15 or j == 18 else None
                style(ws.cell(r, j, v), fmt=fmt, align=LEFT if j in (6, 7) else CENTER)
            r += 1
    last = max(2, r - 1)
    end = L(len(headers))
    for label, rgb in STATUT_COLORS.items():
        ws.conditional_formatting.add(f"S2:S{last}", CellIsRule(operator="equal", formula=[f'"{label}"'],
                                                                fill=fill(rgb), font=Font(color="FFFFFFFF", bold=True)))
    ws.conditional_formatting.add(f"H2:H{last}", CellIsRule(operator="equal", formula=['"Non faite"'],
                                                            fill=fill(RED_FILL), font=Font(color=RED_FONT)))
    ws.conditional_formatting.add(f"H2:H{last}", CellIsRule(operator="equal", formula=['"Brouillon"'],
                                                            fill=fill("FFFFEB9C")))
    ws.conditional_formatting.add(f"J2:O{last}", ColorScaleRule(start_type="num", start_value=0, start_color="FFF8696B",
                                                                mid_type="num", mid_value=seuil_bloc,
                                                                mid_color="FFFFEB84", end_type="num", end_value=1,
                                                                end_color="FF63BE7B"))
    for col, w in zip("ABCDEFGHI", (11, 11, 26, 18, 12, 28, 20, 11, 12)):
        ws.column_dimensions[col].width = w
    for j in range(10, len(headers) + 1):
        ws.column_dimensions[L(j)].width = 12
    ws.freeze_panes = "G2"
    ws.auto_filter.ref = f"A1:{end}{last}"
    return trend


# ========================================================== Plan d'actions
def _sheet_actions(ws, rows):
    headers = ["Secteur", "Station", "Superviseur", "Date de visite", "Bloc", "Points en « Non »", "Constat",
               "Action", "Responsable / Échéance", "Suivi"]
    for i, h in enumerate(headers, 1):
        style(ws.cell(1, i, h), bold=True, color="FFFFFFFF", bg="FF1F4E23")
    ws.row_dimensions[1].height = 30
    r = 2
    for s, c, d, sc in rows:
        if not c or c["status"] != "envoye":
            continue
        elim_non = [lib for code, lib in ELIMINATOIRES if d["answers"].get(code) == "Non"]
        blocks = []
        if elim_non:
            blocks.append(("POINTS ÉLIMINATOIRES", "\n".join(elim_non), d.get("commentaire", ""), ""))
        for cle, titre, items in BLOCS:
            nons = [LIBELLES[code] for code, _, _ in items if d["answers"].get(code) == "Non"]
            if nons:
                blocks.append((titre, "\n".join(nons), d["constats"].get(cle, ""), d["actions"].get(cle, "")))
        for titre, nons, constat, action in blocks:
            vals = [s["secteur"], s["name"], s["sup_name"] or "", _d(d.get("visit_date")), titre, nons, constat,
                    action, d.get("responsable", ""), "Ouvert"]
            for j, v in enumerate(vals, 1):
                style(ws.cell(r, j, v or None), align=LEFT if j in (2, 6, 7, 8, 9) else CENTER,
                      fmt="dd/mm/yyyy" if j == 4 else None,
                      bg="FFFFD9D9" if titre.startswith("POINTS") and j == 5 else None)
            r += 1
    last = max(2, r - 1)
    dv = DataValidation(type="list", formula1='"Ouvert,En cours,Clôturé"', allow_blank=True)
    dv.add(f"J2:J{last}")
    ws.add_data_validation(dv)
    ws.conditional_formatting.add(f"J2:J{last}", CellIsRule(operator="equal", formula=['"Clôturé"'],
                                                            fill=fill(GREEN_FILL), font=Font(color=GREEN_FONT)))
    ws.conditional_formatting.add(f"J2:J{last}", CellIsRule(operator="equal", formula=['"Ouvert"'],
                                                            fill=fill(RED_FILL), font=Font(color=RED_FONT)))
    for col, w in zip("ABCDEFGHIJ", (24, 26, 20, 12, 20, 32, 50, 50, 40, 12)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:J{last}"


# =============================================================== Dashboard
def _sheet_dashboard(ws, week, secteurs, rows, trend, ck_last, eq_last, n_stations):
    ws.sheet_view.showGridLines = False
    navy, green = "FF1F4E79", "FF1F4E23"
    ck = lambda col: f"Checklist!${col}$3:${col}${ck_last}"  # noqa: E731
    cols = _checklist_columns()
    letter = {(t, k): L(i) for i, (t, k, _) in enumerate(cols, 1)}
    G, ST = letter[("global", "")], letter[("statut", "")]

    ws.merge_cells("A1:N1")
    style(ws["A1"], bold=True, size=18, color="FFFFFFFF", bg=navy, border=False,
          align=Alignment(horizontal="left", vertical="center", indent=1)).value = "TABLEAU DE BORD — LOS CHECKLIST"
    ws.row_dimensions[1].height = 34
    ws.merge_cells("A2:N2")
    style(ws["A2"], color="FF404040", border=False, align=Alignment(horizontal="left", indent=1)).value = (
        f"{scoring.week_label(week)}   ·   Inventaire & stock : {scoring.month_label(scoring.month_start(week))}"
        f"   ·   Secteurs : {', '.join(secteurs)}   ·   Généré le {dt.datetime.now():%d/%m/%Y %H:%M}")

    # ---- KPI (formules liées à l'onglet Checklist)
    kpis = [
        ("Stations", f"=COUNTA({ck('D')})", "0", navy),
        ("Checklists envoyées", f"=COUNT({ck(G)})", "0", navy),
        ("Taux de complétion", "=IFERROR(B5/A5,0)", "0%", navy),
        ("Score moyen", f'=IFERROR(AVERAGE({ck(G)}),"")', "0%", navy),
        ("Critique", f'=COUNTIF({ck(ST)},"Critique")', "0", STATUT_COLORS["Critique"]),
        ("À corriger", f'=COUNTIF({ck(ST)},"À corriger")', "0", STATUT_COLORS["À corriger"]),
        ("Conforme", f'=COUNTIF({ck(ST)},"Conforme")', "0", STATUT_COLORS["Conforme"]),
    ]
    kpi_cols = ["A", "B", "C", "D", "E", "F", "G"]
    for col, (label, formula, fmt, color) in zip(kpi_cols, kpis):
        style(ws[f"{col}4"], bold=True, size=9, color="FFFFFFFF", bg=color).value = label
        style(ws[f"{col}5"], bold=True, size=20, color=color, fmt=fmt).value = formula
    ws.row_dimensions[4].height = 30
    ws.row_dimensions[5].height = 40

    # ---- par secteur (formules)
    r0 = 8
    _section(ws, r0 - 1, "PAR SECTEUR", 14, green)
    heads = ["Secteur", "Stations", "Envoyées", "Complétion", "Score moyen"] + \
            [BLOC_NOMS_COURTS[c] for c, _, _ in BLOCS] + ["Critique", "À corriger", "Conforme"]
    for i, h in enumerate(heads, 1):
        style(ws.cell(r0, i, h), bold=True, bg="FFD9D9D9")
    ws.row_dimensions[r0].height = 30
    sect_list = sorted({s["secteur"] for s, *_ in rows})
    for j, sect in enumerate(sect_list, r0 + 1):
        a = f"$A{j}"
        vals = [sect, f"=COUNTIF({ck('A')},{a})", f'=COUNTIFS({ck("A")},{a},{ck(G)},">=0")',
                f"=IFERROR(C{j}/B{j},0)", f'=IFERROR(AVERAGEIFS({ck(G)},{ck("A")},{a}),"")']
        vals += [f'=IFERROR(AVERAGEIFS({ck(letter[("pct", c)])},{ck("A")},{a}),"")' for c, _, _ in BLOCS]
        vals += [f'=COUNTIFS({ck("A")},{a},{ck(ST)},"{lab}")' for lab in STATUT_COLORS]
        for i, v in enumerate(vals, 1):
            style(ws.cell(j, i, v), align=LEFT if i == 1 else CENTER, fmt="0%" if 4 <= i <= 11 else None)
    tot = r0 + 1 + len(sect_list)
    first, lastr = r0 + 1, tot - 1
    tvals = ["TOTAL", f"=SUM(B{first}:B{lastr})", f"=SUM(C{first}:C{lastr})", f"=IFERROR(C{tot}/B{tot},0)",
             f'=IFERROR(AVERAGE({ck(G)}),"")']
    tvals += [f'=IFERROR(AVERAGE({ck(letter[("pct", c)])}),"")' for c, _, _ in BLOCS]
    tvals += [f"=SUM({L(i)}{first}:{L(i)}{lastr})" for i in range(12, 15)]
    for i, v in enumerate(tvals, 1):
        style(ws.cell(tot, i, v), bold=True, bg="FFDDEBF7", fmt="0%" if 4 <= i <= 11 else None,
              align=LEFT if i == 1 else CENTER)
    if lastr >= first:
        ws.conditional_formatting.add(f"D{first}:D{lastr}", DataBarRule(start_type="num", start_value=0, end_type="num",
                                                                        end_value=1, color="FF5B9BD5"))
        ws.conditional_formatting.add(f"E{first}:K{tot}", ColorScaleRule(
            start_type="num", start_value=0.5, start_color="FFF8696B", mid_type="num", mid_value=0.8,
            mid_color="FFFFEB84", end_type="num", end_value=1, end_color="FF63BE7B"))

    # ---- par superviseur (valeurs)
    r = tot + 3
    _section(ws, r - 1, "PAR SUPERVISEUR (semaine)", 14, green)
    for i, h in enumerate(["Superviseur", "Stations", "Envoyées", "Complétion", "Score moyen", "Brouillons",
                           "Critique", "À corriger", "Conforme"], 1):
        style(ws.cell(r, i, h), bold=True, bg="FFD9D9D9")
    by_sup = {}
    for row in rows:
        by_sup.setdefault(row[0]["sup_name"] or "— Non assigné —", []).append(row)
    r += 1
    sup_first = r
    for name in sorted(by_sup):
        g = summarize(by_sup[name])
        vals = [name, g["stations"], g["envoyees"], g["completion"], g["score"], g["brouillons"],
                g["critique"], g["a_corriger"], g["conforme"]]
        for i, v in enumerate(vals, 1):
            style(ws.cell(r, i, v), align=LEFT if i == 1 else CENTER, fmt="0%" if i in (4, 5) else None)
        r += 1
    if r > sup_first:
        ws.conditional_formatting.add(f"D{sup_first}:D{r - 1}", DataBarRule(
            start_type="num", start_value=0, end_type="num", end_value=1, color="FF5B9BD5"))

    # ---- points les plus souvent en « Non » (formules)
    r += 2
    _section(ws, r - 1, "POINTS DE CONTRÔLE — TAUX DE « NON »", 14, green)
    for i, h in enumerate(["Point de contrôle", "", "", "Oui", "Non", "N/A", "% Non"], 1):
        if h or i == 1:
            style(ws.cell(r, i, h), bold=True, bg="FFD9D9D9")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    r += 1
    pts_first = r
    for code in TOUS_LES_POINTS:
        c = letter[("ans", code)]
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        style(ws.cell(r, 1, LIBELLES[code]), align=LEFT, bg="FFFFD9D9" if code.startswith("elim") else None)
        style(ws.cell(r, 4, f'=COUNTIF({ck(c)},"Oui")'))
        style(ws.cell(r, 5, f'=COUNTIF({ck(c)},"Non")'))
        style(ws.cell(r, 6, f'=COUNTIF({ck(c)},"N/A")'))
        style(ws.cell(r, 7, f"=IFERROR(E{r}/(D{r}+E{r}),0)"), bold=True, fmt="0%")
        r += 1
    ws.conditional_formatting.add(f"G{pts_first}:G{r - 1}", DataBarRule(
        start_type="num", start_value=0, end_type="num", end_value=1, color="FFF8696B"))

    # ---- évolution hebdomadaire (valeurs)
    r += 2
    _section(ws, r - 1, "ÉVOLUTION HEBDOMADAIRE", 14, green)
    for i, h in enumerate(["Semaine", "Envoyées", "Complétion", "Score moyen", "Critique", "À corriger",
                           "Conforme"], 1):
        style(ws.cell(r, i, h), bold=True, bg="FFD9D9D9")
    r += 1
    tr_first = r
    for w, g in trend:
        iso = w.isocalendar()
        vals = [f"S{iso[1]:02d}", g["envoyees"], g["completion"] or 0, g["score"], g["critique"],
                g["a_corriger"], g["conforme"]]
        for i, v in enumerate(vals, 1):
            style(ws.cell(r, i, v), fmt="0%" if i in (3, 4) else None)
        r += 1
    tr_last = r - 1

    # ---- équipements : taux de dotation (formules sur Invt_Eqmt)
    r += 2
    _section(ws, r - 1, "INVENTAIRE ÉQUIPEMENTS — DOTATION DU RÉSEAU", 14, green)
    for i, h in enumerate(["Équipement", "", "", "Dotées (Oui)", "Manquants (Non)", "% dotation"], 1):
        if h or i == 1:
            style(ws.cell(r, i, h), bold=True, bg="FFD9D9D9")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    r += 1
    eq_first = r
    col = 8
    for _, _, items in EQUIPEMENTS:
        for key, _, _ in items:
            rng = f"Invt_Eqmt!${L(col)}$4:${L(col)}${eq_last}"
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
            style(ws.cell(r, 1, EQUIPEMENT_LIBELLES[key]), align=LEFT)
            style(ws.cell(r, 4, f'=COUNTIF({rng},"Oui")'))
            style(ws.cell(r, 5, f'=COUNTIF({rng},"Non")'))
            style(ws.cell(r, 6, f"=IFERROR(D{r}/(D{r}+E{r}),0)"), bold=True, fmt="0%")
            r += 1
            col += 1
    ws.conditional_formatting.add(f"F{eq_first}:F{r - 1}", DataBarRule(
        start_type="num", start_value=0, end_type="num", end_value=1, color="FF63BE7B"))

    # ---- stock (formules sur Invt_Stck)
    r += 2
    _section(ws, r - 1, "STOCK — FIABILITÉ PAR SECTEUR", 14, green)
    for i, h in enumerate(["Secteur", "Fiable (Oui)", "Non fiable", "Non renseigné", "% fiable"], 1):
        style(ws.cell(r, i, h), bold=True, bg="FFD9D9D9")
    r += 1
    sk = f"Invt_Stck!$A$4:$A${3 + max(1, n_stations)}"
    se = f"Invt_Stck!$E$4:$E${3 + max(1, n_stations)}"
    for sect in sect_list:
        style(ws.cell(r, 1, sect), align=LEFT)
        style(ws.cell(r, 2, f'=COUNTIFS({sk},$A{r},{se},"Oui")'))
        style(ws.cell(r, 3, f'=COUNTIFS({sk},$A{r},{se},"Non")'))
        style(ws.cell(r, 4, f'=COUNTIF({sk},$A{r})-B{r}-C{r}'))
        style(ws.cell(r, 5, f"=IFERROR(B{r}/(B{r}+C{r}),0)"), bold=True, fmt="0%")
        r += 1

    # ---- tableaux sources des graphiques (colonne Q, discrets)
    src = 17  # colonne Q
    ws.cell(4, src, "Bloc").font = font(True, "FF808080", 8)
    ws.cell(4, src + 1, "Score").font = font(True, "FF808080", 8)
    for i, (c, _, _) in enumerate(BLOCS, 5):
        ws.cell(i, src, BLOC_NOMS_COURTS[c]).font = font(False, "FF808080", 8)
        ws.cell(i, src + 1, f"={L(6 + i - 5)}{tot}").number_format = "0%"
        ws.cell(i, src + 1).font = font(False, "FF808080", 8)
    for i, lab in enumerate(STATUT_COLORS, 12):
        ws.cell(i, src, lab).font = font(False, "FF808080", 8)
        ws.cell(i, src + 1, f"={kpi_cols[4 + i - 12]}5").font = font(False, "FF808080", 8)
    ws.column_dimensions["Q"].hidden = True
    ws.column_dimensions["R"].hidden = True

    # ---- graphiques (colonnes I → P, à droite des KPI)
    ch = BarChart()
    ch.type = "col"
    ch.title = "Taux de complétion par secteur"
    ch.y_axis.number_format = "0%"
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 1
    ch.add_data(Reference(ws, min_col=4, min_row=r0, max_row=lastr), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=first, max_row=lastr))
    _chart_style(ch, "1F4E79")
    ws.add_chart(ch, "P3")

    ch = BarChart()
    ch.type = "bar"
    ch.title = "Score moyen par bloc"
    ch.x_axis.scaling.orientation = "maxMin"
    ch.x_axis.number_format = "0%"
    ch.y_axis.number_format = "0%"
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 1
    ch.add_data(Reference(ws, min_col=src + 1, min_row=4, max_row=10), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=src, min_row=5, max_row=10))
    _chart_style(ch, "1F4E23")
    ws.add_chart(ch, "P20")

    pie = DoughnutChart()
    pie.title = "Répartition des statuts"
    pie.add_data(Reference(ws, min_col=src + 1, min_row=12, max_row=14))
    pie.set_categories(Reference(ws, min_col=src, min_row=12, max_row=14))
    for i, rgb in enumerate(STATUT_COLORS.values()):
        pt = DataPoint(idx=i)
        pt.graphicalProperties.solidFill = rgb[2:]
        pie.series[0].dPt.append(pt)
    pie.dataLabels = _labels()
    pie.visible_cells_only = False
    pie.height, pie.width = 7.5, 12
    ws.add_chart(pie, "P37")

    line = LineChart()
    line.title = "Évolution : complétion et score moyen"
    line.y_axis.number_format = "0%"
    line.y_axis.scaling.min, line.y_axis.scaling.max = 0, 1
    line.add_data(Reference(ws, min_col=3, max_col=4, min_row=tr_first - 1, max_row=tr_last), titles_from_data=True)
    line.set_categories(Reference(ws, min_col=1, min_row=tr_first, max_row=tr_last))
    line.height, line.width = 7.5, 16
    for s, color in zip(line.series, ("5B9BD5", "1F4E23")):
        s.graphicalProperties.line.solidFill = color
        s.graphicalProperties.line.width = 28000
        s.smooth = False
    line.legend.position = "b"
    ws.add_chart(line, "P53")

    for col, w in zip("ABCDEFGHIJKLMN", (30, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 11, 11, 11)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["O"].width = 3
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _section(ws, row, title, width, color):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
    c = ws.cell(row, 1, title)
    c.font = font(True, "FFFFFFFF", 11)
    c.fill = fill(color)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 22


def _chart_style(ch, color):
    ch.legend = None
    ch.height, ch.width = 7.5, 16
    ch.series[0].graphicalProperties.solidFill = color
    ch.series[0].graphicalProperties.line.solidFill = color
    ch.dataLabels = _labels()
    ch.visible_cells_only = False


def _labels():
    lab = DataLabelList()
    lab.showVal = True
    lab.showSerName = lab.showCatName = lab.showLegendKey = lab.showPercent = False
    return lab
