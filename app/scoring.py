"""Calcul des scores — mêmes règles que les formules de la fiche Excel."""
import datetime as dt

from .referentiel import BLOCS, ELIMINATOIRES, STOCK_ECART_TOLERE


def _ratio(oui, non):
    return oui / (oui + non) if (oui + non) else None


def score_checklist(answers, seuil_bloc, seuil_global):
    """Retourne {blocs: {cle: % ou None}, oui, non, global, statut}.

    Reprend les colonnes N/T/AB/AH/AM/AS (par bloc), AT/AU/AV (global) et AW
    (statut) : un « Non » éliminatoire => Critique ; sinon À corriger si le
    global < seuil global ou si un bloc < seuil bloc ; sinon Conforme.
    """
    answers = answers or {}
    blocs, tot_oui, tot_non = {}, 0, 0
    for cle, _, items in BLOCS:
        vals = [answers.get(code) for code, _, _ in items]
        oui, non = vals.count("Oui"), vals.count("Non")
        blocs[cle] = _ratio(oui, non)
        tot_oui += oui
        tot_non += non
    global_ = _ratio(tot_oui, tot_non)
    if any(answers.get(code) == "Non" for code, _ in ELIMINATOIRES):
        statut = "Critique"
    elif global_ is None:
        statut = ""
    else:
        notes = [v for v in blocs.values() if v is not None]
        statut = "À corriger" if (global_ < seuil_global or min(notes) < seuil_bloc) else "Conforme"
    return {"blocs": blocs, "oui": tot_oui, "non": tot_non, "global": global_, "statut": statut}


def ecart_stock(physique, systeme):
    if physique in (None, "") or systeme in (None, "") or not float(systeme):
        return None
    return (float(physique) - float(systeme)) / float(systeme)


def stock_ecart_ok(physique, systeme):
    e = ecart_stock(physique, systeme)
    return None if e is None else abs(e) <= STOCK_ECART_TOLERE


# ---------------------------------------------------------------- Semaines
def week_start(d=None):
    d = d or dt.date.today()
    return d - dt.timedelta(days=d.weekday())


def parse_week(s):
    try:
        return week_start(dt.date.fromisoformat(s))
    except (TypeError, ValueError):
        return week_start()


def week_label(monday):
    iso = monday.isocalendar()
    sunday = monday + dt.timedelta(days=6)
    return f"S{iso[1]:02d} · {monday:%d/%m} → {sunday:%d/%m/%Y}"


def month_start(d=None):
    d = d or dt.date.today()
    return d.replace(day=1)


def parse_month(s):
    try:
        return dt.date.fromisoformat(s[:7] + "-01")
    except (TypeError, ValueError):
        return month_start()


MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def month_label(m):
    return f"{MOIS_FR[m.month - 1].capitalize()} {m.year}"


def pct(v, digits=0):
    return "" if v is None else f"{v * 100:.{digits}f} %"
