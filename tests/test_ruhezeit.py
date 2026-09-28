"""Tests für die Ruhezeit (z. B. 03:00–06:00): nachts nur Dringendes, der Rest kommt danach."""

from datetime import datetime, timezone

import pytest

from bot.einstellungen import KategorieFilter
from bot.lauf import in_ruhezeit
from tests.test_lauf import (
    DELTA,
    GTTG_LISTE,
    GTTG_PRODUKT,
    VORBESTELLBAR,
    FalscherMelder,
    einstellungen,
    html,
    lauf,
)

BERLIN = "Europe/Berlin"
# Die Tests starten am 26.09.2026 um 14:00 Uhr deutscher Zeit (12:00 UTC)
NACHTS = 13 * 60 + 30    # 27.09. 03:30 Uhr
MORGENS = 16 * 60 + 10   # 27.09. 06:10 Uhr


def utc(stunde, minute=0, monat=9, tag=27):
    return datetime(2026, monat, tag, stunde, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize("zeit, erwartet", [
    (utc(1, 0), True),      # 03:00 in Berlin (Sommerzeit, UTC+2) – Beginn zählt dazu
    (utc(3, 59), True),     # 05:59
    (utc(4, 0), False),     # 06:00 – Ende zählt nicht mehr dazu
    (utc(0, 59), False),    # 02:59
    (utc(12, 0), False),    # mittags
    (utc(2, 30, monat=12, tag=1), True),   # Winterzeit (UTC+1): 03:30
    (utc(5, 30, monat=12, tag=1), False),  # Winterzeit: 06:30
])
def test_in_ruhezeit(zeit, erwartet):
    assert in_ruhezeit("03:00-06:00", zeit, BERLIN) is erwartet


def test_ruhezeit_ueber_mitternacht_und_ohne():
    assert in_ruhezeit("22:00-06:00", utc(21, 30), BERLIN)          # 23:30
    assert in_ruhezeit("22:00-06:00", utc(2, 0), BERLIN)            # 04:00
    assert not in_ruhezeit("22:00-06:00", utc(10, 0), BERLIN)       # 12:00
    assert not in_ruhezeit(None, utc(1, 30), BERLIN)


def mit_uebersicht(**regeln):
    """Ein Produkt (wird VORBESTELLBAR = dringend) + eine neue Liste (Übersicht = nicht dringend)."""
    return einstellungen(DELTA, kategorien=[("GTTG Vorverkauf", GTTG_LISTE)],
                         filter_=KategorieFilter(nur_mit=["Display"]), ruhezeit="03:00-06:00", **regeln)


SEITEN = {GTTG_PRODUKT: VORBESTELLBAR, GTTG_LISTE: html("gate_to_the_games/liste_vorverkauf.html")}


def test_nachts_nur_dringendes_der_rest_kommt_morgens(speicher):
    melder = FalscherMelder()
    e = mit_uebersicht()
    lauf(e, speicher, SEITEN, melder, minuten=NACHTS)
    # Um 03:30 kommt nur der Ping fürs vorbestellbare Produkt
    assert melder.titel == ["🔵 VORBESTELLBAR – Delta Display"]
    assert [n["text"].split(" – ")[0] for n in melder.nachrichten] == ["🛒 JETZT KAUFBAR"]

    # Um 06:10: die zurückgehaltene Übersicht kommt – der Ping NICHT noch einmal
    lauf(e, speicher, SEITEN, melder, minuten=MORGENS)
    zweiter = [k.titel for k in melder.nachrichten[-1]["kaesten"]]
    assert "📋 Neu überwacht: GTTG Vorverkauf" in zweiter
    assert melder.titel.count("🔵 VORBESTELLBAR – Delta Display") == 1

    # Danach ist alles erledigt
    anzahl = len(melder.nachrichten)
    lauf(e, speicher, SEITEN, melder, minuten=MORGENS + 60)
    assert len(melder.nachrichten) == anzahl


def test_nachts_gar_nichts_wenn_so_eingestellt(speicher):
    melder = FalscherMelder()
    e = mit_uebersicht(in_ruhezeit_nur_dringend=False)
    lauf(e, speicher, SEITEN, melder, minuten=NACHTS)
    assert melder.nachrichten == []
    lauf(e, speicher, SEITEN, melder, minuten=MORGENS)
    assert "🔵 VORBESTELLBAR – Delta Display" in melder.titel        # kommt jetzt – nichts geht verloren
    assert any(t.startswith("📋 Neu überwacht") for t in melder.titel)


def test_tagsueber_ist_alles_wie_immer(speicher):
    melder = FalscherMelder()
    lauf(mit_uebersicht(), speicher, SEITEN, melder)                 # 14:00 Uhr
    assert "🔵 VORBESTELLBAR – Delta Display" in melder.titel
    assert "📋 Neu überwacht: GTTG Vorverkauf" in melder.titel
