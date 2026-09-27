"""Tests für Games Island (crawlme.games-island.eu) – mit einer echten, gekürzten Seite."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from bot.abruf import sperre_erkennen
from bot.adapter import ADAPTER, adapter_fuer
from bot.discord import Kasten
from bot.einstellungen import KategorieFilter
from bot.pings import ping_kasten
from bot.status import Status
from tests.test_lauf import FalscherMelder, einstellungen, lauf, speicher  # noqa: F401 (speicher = Fixture)

BEISPIELE = Path(__file__).parent / "beispiele" / "games_island"
HEUTE = date(2026, 9, 27)
LISTE = (BEISPIELE / "liste_booster_displays.html").read_text(encoding="utf-8")
NICHT_GEFUNDEN = (BEISPIELE / "nicht_gefunden.html").read_text(encoding="utf-8")

KATEGORIE = "https://games-island.eu/c/Pokemon/Booster-Displays"
KATEGORIE_ABRUF = "https://crawlme.games-island.eu/c/Pokemon/Booster-Displays"
PITCH_BLACK = "https://games-island.eu/Pokemon-TCG-Mega-Evolution-05-Pitch-Black-Booster-Display-18-Boosters-Englisch"
FATALE_FLAMMEN = "https://games-island.eu/Pokemon-TCG-Mega-Entwicklung-02-Fatale-Flammen-Booster-Display-Deutsch"

GI = adapter_fuer(KATEGORIE)


def test_adapter_wird_gefunden_und_laedt_von_crawlme():
    assert GI is not None and GI.name == "Games Island"
    assert adapter_fuer(KATEGORIE_ABRUF) is GI  # auch wenn jemand die crawlme-Adresse einträgt
    assert GI.abruf_url(KATEGORIE) == KATEGORIE_ABRUF
    assert GI.abruf_url(KATEGORIE_ABRUF) == KATEGORIE_ABRUF
    assert GI.abruf_url(PITCH_BLACK).startswith("https://crawlme.games-island.eu/Pokemon-TCG-Mega-Evolution-05")
    assert GI.abruf_domains() == ("crawlme.games-island.eu",)
    assert GI.treffer_pro_seite == 0  # keine Shop-Suche – dafür gibt es die Kategorien


def test_pause_haelt_das_limit_ein():
    # Erlaubt sind 5 Anfragen in 5 Minuten
    assert GI.min_abstand_sekunden * 5 >= 300
    assert GI in ADAPTER


def test_liste_erkennt_status_und_termine():
    eintraege = {e.url: e.ergebnis for e in GI.erkenne_liste(LISTE, KATEGORIE_ABRUF, HEUTE)}
    assert eintraege[PITCH_BLACK].status == Status.BESTELLBAR
    assert eintraege[PITCH_BLACK].titel == "Pokemon TCG - Mega Evolution 05: Pitch Black Booster Display (18 Boosters) - Englisch"
    assert eintraege[FATALE_FLAMMEN].status == Status.AUSVERKAUFT

    vorverkauf = eintraege["https://games-island.eu/MTG-Phyrexia-All-Will-Be-One-Set-Booster-Display-Englisch"]
    assert vorverkauf.status == Status.VORBESTELLBAR
    assert vorverkauf.liefertermin == "04.11.2026"
    angekuendigt = next(e for u, e in eintraege.items() if "Holiday-Jumpstart" in u)
    assert angekuendigt.status == Status.BALD
    assert angekuendigt.liefertermin == "04.11.2026"

    # Keine Preise (Wunsch von Games Island) – im Ping steht dann „Preis im Shop“
    assert all(e.preis is None and e.ohne_preis for e in eintraege.values())
    # Kategorie-Überschriften sind keine Produkte, doppelte Produkte zählen nur einmal
    assert len(eintraege) == 10  # 11 Zeilen, eine davon doppelt
    assert all(u.startswith("https://games-island.eu/") for u in eintraege)


def test_titel_mit_sonderzeichen():
    eintraege = {e.url: e.ergebnis for e in GI.erkenne_liste(LISTE, KATEGORIE_ABRUF, HEUTE)}
    titel = eintraege["https://games-island.eu/Pokemon-TCG-Scarlet-Violet-85-Prismatic-Evolutions-Booster-Bundle-Englisch"].titel
    assert titel == "Pokemon TCG - Scarlet & Violet 8.5: Prismatic Evolutions Booster Bundle - Englisch"


def test_einzelnes_produkt():
    assert GI.erkenne_produkt(LISTE, PITCH_BLACK, HEUTE).status == Status.BESTELLBAR
    assert GI.erkenne_produkt(LISTE, FATALE_FLAMMEN + "/", HEUTE).status == Status.AUSVERKAUFT


def test_nicht_gefunden_gilt_als_ausverkauft():
    ergebnis = GI.erkenne_produkt(NICHT_GEFUNDEN, "https://games-island.eu/Pokemon", HEUTE)
    assert ergebnis.status == Status.AUSVERKAUFT
    assert ergebnis.hinweis


def test_leere_seite_ist_unbekannt():
    ergebnis = GI.erkenne_produkt("<html><body>Wartung</body></html>", PITCH_BLACK, HEUTE)
    assert ergebnis.status == Status.UNBEKANNT


def test_unbekannter_status_ist_unbekannt():
    html = ('<table><tr class="artikel status_Irgendwas"><td><a href="https://games-island.eu/X-Display">'
            'X Display</a></td><td>Irgendwas</td></tr></table>')
    (eintrag,) = GI.erkenne_liste(html, KATEGORIE_ABRUF, HEUTE)
    assert eintrag.ergebnis.status == Status.UNBEKANNT


def test_crawlme_seite_gilt_nicht_als_sperre():
    antwort = SimpleNamespace(url=KATEGORIE_ABRUF, status_code=200, text=LISTE)
    assert sperre_erkennen(antwort) is None
    gebannt = SimpleNamespace(url="https://banned.games-island.eu/", status_code=200, text="")
    assert sperre_erkennen(gebannt)


def test_ping_zeigt_keinen_preis():
    eintrag = next(e for e in GI.erkenne_liste(LISTE, KATEGORIE_ABRUF, HEUTE) if e.url == PITCH_BLACK)
    kasten: Kasten = ping_kasten("Pitch Black Display", "Games Island", PITCH_BLACK, eintrag.ergebnis, None,
                                 "neu", shop_vertraut=True, aus_kategorie=True)
    assert "Preis im Shop" in kasten.text
    assert "€" not in kasten.text
    assert kasten.link == PITCH_BLACK  # Link für Menschen zeigt auf games-island.eu


def test_lauf_holt_kategorie_ueber_crawlme(speicher):  # noqa: F811
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("Games Island – Booster Displays", KATEGORIE)],
                      filter_=KategorieFilter(nur_mit=["Display", "Booster Bundle"], ohne=["Koreanisch"]))
    e.vertrauenswuerdige_shops.append("games-island.eu")
    _, abrufer = lauf(e, speicher, {KATEGORIE_ABRUF: LISTE}, melder)
    assert abrufer.abgerufen == [KATEGORIE_ABRUF]
    (kasten,) = [k for n in melder.nachrichten for k in n["kaesten"]]
    assert kasten.titel == "📋 Neu überwacht: Games Island – Booster Displays"
    assert "Pitch Black" in kasten.text and "Preis im Shop" in kasten.text
    assert "Koreanisch" not in kasten.text
    assert kasten.link == KATEGORIE

    # Später: Fatale Flammen wieder da → Ping mit Link zu games-island.eu
    wieder_da = LISTE.replace(
        'status_Ausverkauft"><td><a href="' + FATALE_FLAMMEN + '"',
        'status_aufLager"><td><a href="' + FATALE_FLAMMEN + '"')
    assert wieder_da != LISTE
    lauf(e, speicher, {KATEGORIE_ABRUF: wieder_da}, melder, minuten=20)
    letzte = melder.nachrichten[-1]["kaesten"]
    assert [k.titel for k in letzte] == [
        "🟢 BESTELLBAR – Pokemon TCG - Mega-Entwicklung 02: Fatale Flammen Booster Display - Deutsch"]
    assert letzte[0].link == FATALE_FLAMMEN
    assert "Vorher: AUSVERKAUFT" in letzte[0].text
