"""Tests für den kompletten Lauf – mit echten Beispielseiten, aber ohne Internet.

Die Attrappen ersetzen den Abruf (liefert gespeicherte Seiten) und Discord
(merkt sich, was geschickt worden wäre).
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from bot.abruf import Seite
from bot.discord import DiscordFehler
from bot.einstellungen import (
    Allgemein,
    Einstellungen,
    Kategorie,
    KategorieFilter,
    Produkt,
    Regeln,
)
from bot.lauf import Lauf
from bot.speicher import Speicher
from bot.status import Status
from tests.hilfen import ohne_ausverkauft_markierung

BEISPIELE = Path(__file__).parent / "beispiele"
HEUTE = date(2026, 9, 26)
START = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

GTTG_PRODUKT = "https://www.gate-to-the-games.de/Delta-Display"
GTTG_LISTE = "https://www.gate-to-the-games.de/Pokemon-Karten/Pokemon-Sammelkarten/"
CC_NEU = "https://www.card-corner.de/Neu-Eingetroffen"


def html(name: str) -> str:
    return (BEISPIELE / name).read_text(encoding="utf-8")


# Echte Seite einer (inzwischen ausverkauften) Vorbestellung – ohne Banner = noch bestellbar
VORBESTELLUNG_AUSVERKAUFT = html("gate_to_the_games/produkt_vorbestellung_ausverkauft.html")
VORBESTELLBAR = ohne_ausverkauft_markierung(VORBESTELLUNG_AUSVERKAUFT)
AUSVERKAUFT = html("gate_to_the_games/produkt_ausverkauft.html")


class FalscherAbrufer:
    def __init__(self, seiten: dict):
        self.seiten = seiten  # url -> html-Text oder fertige Seite
        self.abgerufen = []

    def hole(self, url):
        self.abgerufen.append(url)
        inhalt = self.seiten[url]
        return inhalt if isinstance(inhalt, Seite) else Seite(url, text=inhalt, http=200)


class FalscherMelder:
    def __init__(self, kaputt=False):
        self.nachrichten = []
        self.kaputt = kaputt

    def sende(self, text="", kaesten=None):
        if self.kaputt:
            raise DiscordFehler("Discord ist gerade nicht erreichbar (Test).")
        self.nachrichten.append({"text": text, "kaesten": kaesten})

    @property
    def titel(self):
        return [k.titel for n in self.nachrichten for k in n["kaesten"]]


def einstellungen(watchlist=None, kategorien=None, filter_=None, **regeln):
    standard = Regeln(**regeln)
    return Einstellungen(
        allgemein=Allgemein(),
        standard_regeln=standard,
        vertrauenswuerdige_shops=["gate-to-the-games.de", "card-corner.de"],
        watchlist=[Produkt(name, links, standard) for name, links in (watchlist or [])],
        kategorien=[Kategorie(name, link) for name, link in (kategorien or [])],
        kategorie_filter=filter_ or KategorieFilter(),
    )


@pytest.fixture
def speicher(tmp_path):
    s = Speicher(tmp_path / "bot.db")
    yield s
    s.schliessen()


def lauf(e, speicher, seiten, melder, minuten=0):
    """Führt einen Lauf aus – 'minuten' nach dem ersten Lauf."""
    abrufer = FalscherAbrufer(seiten)
    ergebnis = Lauf(e, speicher, abrufer, melder, jetzt=START + timedelta(minutes=minuten), heute=HEUTE).starten()
    return ergebnis, abrufer


DELTA = [("Delta Display", [GTTG_PRODUKT])]


def test_erster_check_meldet_vorbestellung(speicher):
    melder = FalscherMelder()
    code, _ = lauf(einstellungen(DELTA), speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder)
    assert code == 0
    assert melder.titel == ["🔵 VORBESTELLBAR – Delta Display"]
    kasten = melder.nachrichten[0]["kaesten"][0]
    assert "199,90 €" in kasten.text
    assert "06.11.2026" in kasten.text
    assert kasten.link == GTTG_PRODUKT
    # Kurztext für die iPhone-Mitteilung
    assert melder.nachrichten[0]["text"] == "🔵 VORBESTELLBAR – Delta Display"


def test_kein_spam_bei_gleichem_stand(speicher):
    melder = FalscherMelder()
    e = einstellungen(DELTA)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=15)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=30)
    assert len(melder.nachrichten) == 1
    assert speicher.anzahl_checks() == 3  # Verlauf wird trotzdem gespeichert


def test_ausverkauft_zu_vorbestellbar_wird_gemeldet(speicher):
    melder = FalscherMelder()
    e = einstellungen(DELTA)
    lauf(e, speicher, {GTTG_PRODUKT: AUSVERKAUFT}, melder)
    assert melder.nachrichten == []  # AUSVERKAUFT pingt nicht
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=15)
    kasten = melder.nachrichten[0]["kaesten"][0]
    assert kasten.titel.startswith("🔵 VORBESTELLBAR")
    assert "Vorher: AUSVERKAUFT" in kasten.text


def test_maximalpreis_verhindert_ping(speicher):
    melder = FalscherMelder()
    lauf(einstellungen(DELTA, max_preis=150), speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder)
    assert melder.nachrichten == []


def test_unbekannt_aendert_nichts_am_letzten_stand(speicher):
    melder = FalscherMelder()
    e = einstellungen(DELTA)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder)
    lauf(e, speicher, {GTTG_PRODUKT: "<html>Wartung</html>"}, melder, minuten=15)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=30)
    # Kurzer Aussetzer → kein zweiter Ping für denselben Stand
    assert len(melder.nachrichten) == 1
    assert speicher.stand(GTTG_PRODUKT)[0] == Status.VORBESTELLBAR


def test_kein_ping_geht_verloren_wenn_discord_ausfaellt(speicher):
    e = einstellungen(DELTA)
    with pytest.raises(DiscordFehler):
        lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, FalscherMelder(kaputt=True))
    assert speicher.stand(GTTG_PRODUKT) is None  # nicht als „gemeldet“ gespeichert
    melder = FalscherMelder()
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=15)
    assert melder.titel == ["🔵 VORBESTELLBAR – Delta Display"]


def test_sperre_wird_einmal_gemeldet_und_nicht_umgangen(speicher):
    melder = FalscherMelder()
    e = einstellungen([("A", [GTTG_PRODUKT, GTTG_PRODUKT + "-2"])])
    gesperrt = Seite(GTTG_PRODUKT, http=403, problem="Seite blockt den Bot (HTTP 403)", gesperrt=True)
    _, abrufer = lauf(e, speicher, {GTTG_PRODUKT: gesperrt, GTTG_PRODUKT + "-2": gesperrt}, melder)
    assert abrufer.abgerufen == [GTTG_PRODUKT]  # nach der Sperre keine weiteren Anfragen
    assert melder.titel == ["⚠️ Gate to the Games blockt den Bot"]
    lauf(e, speicher, {GTTG_PRODUKT: gesperrt, GTTG_PRODUKT + "-2": gesperrt}, melder, minuten=15)
    assert len(melder.nachrichten) == 1  # nicht nochmal
    lauf(e, speicher, {GTTG_PRODUKT: AUSVERKAUFT, GTTG_PRODUKT + "-2": AUSVERKAUFT}, melder, minuten=30)
    assert melder.titel[-1] == "✅ Gate to the Games ist wieder erreichbar"


def test_shop_wird_nicht_zu_oft_abgefragt(speicher):
    melder = FalscherMelder()
    e = einstellungen(DELTA)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder)
    _, abrufer = lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=5)
    assert abrufer.abgerufen == []
    _, abrufer = lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=13)
    assert abrufer.abgerufen == [GTTG_PRODUKT]


def test_verbotener_shop_wird_nie_abgefragt(speicher):
    melder = FalscherMelder()
    e = einstellungen([("GI", ["https://games-island.eu/Pokemon-Display"]),
                       ("GI 2", ["https://games-island.eu/Pokemon-ETB"])])
    _, abrufer = lauf(e, speicher, {}, melder)
    assert abrufer.abgerufen == []
    assert melder.titel == ["🚫 games-island.eu wird nicht automatisch geprüft"]
    lauf(e, speicher, {}, melder, minuten=15)
    assert len(melder.nachrichten) == 1  # Hinweis nur einmal


def test_kategorie_erster_blick_schickt_uebersicht(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GTTG Vorverkauf", GTTG_LISTE)],
                      filter_=KategorieFilter(nur_mit=["Display", "Top Trainer"]))
    liste = ohne_ausverkauft_markierung(html("gate_to_the_games/liste_vorverkauf.html"))
    lauf(e, speicher, {GTTG_LISTE: liste}, melder)
    assert melder.titel == ["📋 Neu überwacht: GTTG Vorverkauf"]
    text = melder.nachrichten[0]["kaesten"][0].text
    assert "Delta Herrschaft Display" in text
    assert "Booster (deutsch)" not in text  # vom Filter aussortiert
    # Zweiter Lauf, nichts Neues → still
    lauf(e, speicher, {GTTG_LISTE: liste}, melder, minuten=15)
    assert len(melder.nachrichten) == 1


def test_ausverkaufte_vorbestellungen_tauchen_nicht_in_der_uebersicht_auf(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GTTG Vorverkauf", GTTG_LISTE)],
                      filter_=KategorieFilter(nur_mit=["Display", "Top Trainer"]))
    lauf(e, speicher, {GTTG_LISTE: html("gate_to_the_games/liste_vorverkauf.html")}, melder)
    text = melder.nachrichten[0]["kaesten"][0].text
    assert "davon 0 gerade interessant" in text
    assert "Delta Herrschaft Display" not in text


def test_ausverkaufte_vorbestellung_pingt_nicht(speicher):
    melder = FalscherMelder()
    lauf(einstellungen(DELTA), speicher, {GTTG_PRODUKT: VORBESTELLUNG_AUSVERKAUFT}, melder)
    assert melder.nachrichten == []
    # Wird das Kontingent wieder aufgestockt, kommt der Ping
    lauf(einstellungen(DELTA), speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder, minuten=15)
    assert melder.titel == ["🔵 VORBESTELLBAR – Delta Display"]


def test_kategorie_neues_produkt_wird_gemeldet(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("CC Neu", CC_NEU)], filter_=KategorieFilter(nur_mit=["Display"]))
    seiten = {CC_NEU: html("card_corner/liste_neu_eingetroffen.html")}
    lauf(e, speicher, seiten, melder)
    # So tun, als wäre dieses Display beim ersten Mal noch nicht im Shop gewesen
    speicher._db.execute("DELETE FROM stand WHERE url LIKE '%Pokemon-Abyss-Eye-Display-Koreanisch'")
    speicher._db.commit()
    lauf(e, speicher, seiten, melder, minuten=15)
    neu = melder.nachrichten[-1]["kaesten"]
    assert [k.titel for k in neu] == ["🟢 BESTELLBAR – Pokemon Abyss Eye Display (Koreanisch)"]
    assert "Neu im Shop" in neu[0].text
    assert "45,99 €" in neu[0].text


def test_kategorie_filter_ohne(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("CC Neu", CC_NEU)],
                      filter_=KategorieFilter(nur_mit=["Display"], ohne=["Koreanisch"]))
    lauf(e, speicher, {CC_NEU: html("card_corner/liste_neu_eingetroffen.html")}, melder)
    assert "Koreanisch" not in melder.nachrichten[0]["kaesten"][0].text


def test_ohne_discord_wird_nichts_als_gemeldet_gespeichert(speicher):
    e = einstellungen(DELTA)
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR}, melder=None)
    assert speicher.stand(GTTG_PRODUKT) is None  # kommt, sobald Discord eingerichtet ist
