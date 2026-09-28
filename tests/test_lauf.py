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


def einstellungen(watchlist=None, kategorien=None, filter_=None, suche=None, **regeln):
    standard = Regeln(**regeln)
    return Einstellungen(
        allgemein=Allgemein(),
        standard_regeln=standard,
        vertrauenswuerdige_shops=["gate-to-the-games.de", "card-corner.de"],
        watchlist=[Produkt(name, links, standard) for name, links in (watchlist or [])]
                  + [Produkt(name, [], standard, suche=begriffe) for name, begriffe in (suche or [])],
        kategorien=[Kategorie(name, link) for name, link in (kategorien or [])],
        kategorie_filter=filter_ or KategorieFilter(),
    )


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
    assert melder.nachrichten[0]["text"] == "🛒 JETZT KAUFBAR – 🔵 VORBESTELLBAR – Delta Display"


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
    e = einstellungen([("Netto", ["https://www.netto-online.de/pokemon-display"]),
                       ("Netto 2", ["https://www.netto-online.de/pokemon-etb"])])
    _, abrufer = lauf(e, speicher, {}, melder)
    assert abrufer.abgerufen == []
    assert melder.titel == ["🚫 netto-online.de wird nicht automatisch geprüft"]
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
    assert "davon 0 gerade verfügbar" in text
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


# --- Watchlist per Suchbegriff (Sets) -------------------------------------------------

LEER = "<html><body>Keine Treffer</body></html>"
SET_FILTER = KategorieFilter(
    nur_mit=["Display", "Top Trainer", "Elite Trainer", "Booster Bundle", "Collection", "Kollektion"],
    ohne=["Blister", "Illustration Rare", "B-Ware"],
)
FATALE = [("Fatale Flammen", ["Fatale Flammen", "Phantasmal Flames"])]
GTTG_SUCHE = "https://www.gate-to-the-games.de/?suche={}&af=100"
CC_SUCHE = "https://www.card-corner.de/?suche={}&af=50"


def suchseiten():
    return {
        GTTG_SUCHE.format("Fatale+Flammen"): html("gate_to_the_games/suche_fatale_flammen.html"),
        GTTG_SUCHE.format("Fatale+Flammen") + "&seite=2": LEER,
        GTTG_SUCHE.format("Phantasmal+Flames"): html("gate_to_the_games/suche_phantasmal_flames.html"),
        CC_SUCHE.format("Fatale+Flammen"): LEER,
        CC_SUCHE.format("Phantasmal+Flames"): LEER,
    }


def test_set_suche_schickt_beim_ersten_mal_eine_uebersicht(speicher):
    melder = FalscherMelder()
    _, abrufer = lauf(einstellungen(suche=FATALE, filter_=SET_FILTER), speicher, suchseiten(), melder)
    assert melder.titel == ["📋 Neu überwacht: Fatale Flammen bei Gate to the Games",
                            "📋 Neu überwacht: Fatale Flammen bei Card-Corner"]
    gttg, cc = (k.text for k in melder.nachrichten[0]["kaesten"])
    assert "Fatale Flammen Display (36 Booster) (deutsch)" in gttg      # bestellbar → steht drin
    assert "Fatale Flammen Top Trainer Box (deutsch)" in gttg
    assert "Booster Bundle" not in gttg                                  # ausverkauft → nicht in der Liste
    assert "Illustration Rare" not in gttg                               # Einzelkarte → vom Filter aussortiert
    assert "Gerade keine passenden Produkte" in cc
    # Seite 1 war voll (100 Treffer) → Seite 2 wurde auch geholt; bei 11 Treffern nicht
    assert GTTG_SUCHE.format("Fatale+Flammen") + "&seite=2" in abrufer.abgerufen
    assert GTTG_SUCHE.format("Phantasmal+Flames") + "&seite=2" not in abrufer.abgerufen


def test_set_suche_meldet_restock(speicher):
    melder = FalscherMelder()
    e = einstellungen(suche=FATALE, filter_=SET_FILTER)
    lauf(e, speicher, suchseiten(), melder)
    # So tun, als wäre das Display beim letzten Mal ausverkauft gewesen
    display = "https://www.gate-to-the-games.de/Pokemon-Karten-Mega-Entwicklung-Fatale-Flammen-Display-36-Booster-deutsch"
    assert speicher.stand(display) is not None
    speicher.setze_stand(display, "Gate to the Games", "Display", Status.AUSVERKAUFT, 399.90)
    lauf(e, speicher, suchseiten(), melder, minuten=15)
    kasten = melder.nachrichten[-1]["kaesten"][0]
    assert kasten.titel == "🟢 BESTELLBAR – Mega-Entwicklung Fatale Flammen Display (36 Booster) (deutsch)"
    assert "Vorher: AUSVERKAUFT" in kasten.text


def test_set_suche_nur_treffer_mit_dem_namen(speicher):
    melder = FalscherMelder()
    e = einstellungen(suche=[("Dunkelnacht", ["Pitch Black"])], filter_=SET_FILTER)
    seiten = {GTTG_SUCHE.format("Pitch+Black"): LEER,
              CC_SUCHE.format("Pitch+Black"): html("card_corner/suche_pitch_black.html")}
    lauf(e, speicher, seiten, melder)
    text = melder.nachrichten[0]["kaesten"][1].text
    assert "Pitch Black Elite Trainer Box" in text
    assert "B-Ware" not in text


def test_viele_neue_eintraege_auf_einmal_ergeben_eine_sammelnachricht(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("CC Neu", CC_NEU)])
    seiten = {CC_NEU: html("card_corner/liste_neu_eingetroffen.html")}
    lauf(e, speicher, seiten, melder)
    # So tun, als wäre die Liste plötzlich viel länger geworden (alle Produkte „unbekannt“)
    speicher._db.execute("DELETE FROM stand")
    speicher._db.commit()
    lauf(e, speicher, seiten, melder, minuten=15)
    neu = melder.nachrichten[-1]["kaesten"]
    assert [k.titel for k in neu] == ["🗂️ Viele neue Einträge: CC Neu"]
    assert "Vermutlich hat der Shop die Liste umgestellt" in neu[0].text
    # Danach sind die Produkte bekannt → beim nächsten Lauf Ruhe
    lauf(e, speicher, seiten, melder, minuten=30)
    assert len(melder.nachrichten) == 2


def test_uebersicht_beachtet_maximalpreis(speicher):
    melder = FalscherMelder()
    e = einstellungen(suche=FATALE, filter_=SET_FILTER, max_preis=200)
    lauf(e, speicher, suchseiten(), melder)
    gttg = melder.nachrichten[0]["kaesten"][0].text
    assert "Top Trainer Box (deutsch)" in gttg          # 149,90 € → unter 200 €
    assert "Display (36 Booster) (deutsch)" not in gttg  # 399,90 € → zu teuer


def test_kaufbares_und_infos_kommen_getrennt(speicher):
    melder = FalscherMelder()
    e = einstellungen(DELTA, kategorien=[("GTTG Vorverkauf", GTTG_LISTE)],
                      filter_=KategorieFilter(nur_mit=["Display"]))
    liste = html("gate_to_the_games/liste_vorverkauf.html")
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR, GTTG_LISTE: liste}, melder)
    # Zwei Nachrichten = zwei Mitteilungen: zuerst das Kaufbare, dann die Übersicht
    assert [n["text"].split(" – ")[0] for n in melder.nachrichten] == ["🛒 JETZT KAUFBAR", "ℹ️ Übersicht & Hinweise"]
    assert [k.titel for k in melder.nachrichten[0]["kaesten"]] == ["🔵 VORBESTELLBAR – Delta Display"]
    assert melder.nachrichten[1]["kaesten"][0].titel == "📋 Neu überwacht: GTTG Vorverkauf"


def test_neues_set_verschluckt_kein_wieder_da(speicher):
    """Ein Produkt ist schon bekannt (ausverkauft). Dann kommt sein Set neu auf die Watchlist, und beim
    ersten Blick ist es wieder bestellbar → das muss trotz Übersicht einzeln gemeldet werden."""
    melder = FalscherMelder()
    display = "https://www.gate-to-the-games.de/Pokemon-Karten-Mega-Entwicklung-Fatale-Flammen-Display-36-Booster-deutsch"
    speicher.setze_stand(display, "Gate to the Games", "Display", Status.AUSVERKAUFT, 399.90, START)
    lauf(einstellungen(suche=FATALE, filter_=SET_FILTER), speicher, suchseiten(), melder)
    titel = melder.titel
    assert "🟢 BESTELLBAR – Mega-Entwicklung Fatale Flammen Display (36 Booster) (deutsch)" in titel
    assert any(t.startswith("📋 Neu überwacht: Fatale Flammen") for t in titel)
    assert melder.nachrichten[0]["text"].startswith("🛒 JETZT KAUFBAR")  # Kaufbares zuerst


def test_status_zeigt_nur_kuerzlich_gesehene_produkte(speicher):
    alt, neu = "https://www.card-corner.de/alt", "https://www.card-corner.de/neu"
    speicher.setze_stand(alt, "Card-Corner", "Altes Display", Status.BESTELLBAR, 100.0, START - timedelta(days=3))
    speicher.setze_stand(neu, "Card-Corner", "Neues Display", Status.BESTELLBAR, 100.0, START)
    speicher.setze_stand("https://www.card-corner.de/weg", "Card-Corner", "Weg", Status.AUSVERKAUFT, 1.0, START)
    statusse = [Status.BESTELLBAR, Status.VORBESTELLBAR]
    assert {z["url"] for z in speicher.verfuegbare(statusse)} == {alt, neu}
    assert [z["url"] for z in speicher.verfuegbare(statusse, gesehen_seit=START - timedelta(hours=24))] == [neu]


def test_unveraenderte_produkte_gelten_als_gesehen(speicher):
    melder = FalscherMelder()
    e = einstellungen(suche=FATALE, filter_=SET_FILTER)
    lauf(e, speicher, suchseiten(), melder)
    lauf(e, speicher, suchseiten(), melder, minuten=60 * 30)  # 30 Stunden später, nichts geändert
    gesehen = speicher.verfuegbare([Status.BESTELLBAR], gesehen_seit=START + timedelta(hours=29))
    assert gesehen  # die Produkte wurden beim zweiten Lauf wieder gesehen


def test_kaputte_quelle_stoppt_nicht_den_ganzen_lauf(speicher, monkeypatch):
    from bot.adapter.jtl import JtlShop

    melder = FalscherMelder()
    e = einstellungen(DELTA, kategorien=[("CC Neu", CC_NEU)])
    original = JtlShop.erkenne_liste

    def kaputt(self, html, url, heute=None):
        if "card-corner" in url:
            raise ValueError("völlig kaputte Seite")
        return original(self, html, url, heute)

    monkeypatch.setattr(JtlShop, "erkenne_liste", kaputt)
    code, _ = lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR, CC_NEU: "<html></html>"}, melder)
    assert code == 0
    assert "🔵 VORBESTELLBAR – Delta Display" in melder.titel          # der Rest läuft weiter
    assert "⚠️ Fehler beim Prüfen: CC Neu" in melder.titel
    lauf(e, speicher, {GTTG_PRODUKT: VORBESTELLBAR, CC_NEU: "<html></html>"}, melder, minuten=20)
    assert melder.titel.count("⚠️ Fehler beim Prüfen: CC Neu") == 1  # Warnung nur einmal


def test_filter_aenderung_gibt_eine_uebersicht_statt_vieler_pings(speicher):
    """Neue Wörter im Filter (z. B. Mini-Tins): Die Produkte sind schon lange im Shop – also keine
    „Neu im Shop“-Pings, sondern EINE Übersicht. Danach ganz normal."""
    melder = FalscherMelder()
    nur_display = KategorieFilter(nur_mit=["Display"])
    liste = html("gate_to_the_games/liste_vorverkauf.html")
    lauf(einstellungen(kategorien=[("GTTG", GTTG_LISTE)], filter_=nur_display), speicher, {GTTG_LISTE: liste}, melder)
    assert melder.titel == ["📋 Neu überwacht: GTTG"]

    mehr = KategorieFilter(nur_mit=["Display", "Top Trainer", "Booster Bundle", "Kollektion"])
    e = einstellungen(kategorien=[("GTTG", GTTG_LISTE)], filter_=mehr)
    lauf(e, speicher, {GTTG_LISTE: liste}, melder, minuten=20)
    zweiter = [k.titel for k in melder.nachrichten[-1]["kaesten"]]
    assert len(zweiter) == 1 and zweiter[0].startswith("🔧 Filter geändert – ")
    assert not any("Neu im Shop" in k.text for n in melder.nachrichten for k in n["kaesten"])

    anzahl = len(melder.nachrichten)
    lauf(e, speicher, {GTTG_LISTE: liste}, melder, minuten=40)   # gleicher Filter → still
    assert len(melder.nachrichten) == anzahl


def test_neues_produkt_nach_filter_aenderung_wird_wieder_einzeln_gemeldet(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GTTG", GTTG_LISTE)], filter_=KategorieFilter(nur_mit=["Display"]))
    liste = ohne_ausverkauft_markierung(html("gate_to_the_games/liste_vorverkauf.html"))
    lauf(e, speicher, {GTTG_LISTE: liste}, melder)
    # Ein verfügbares Produkt „verschwindet“ aus dem Speicher = taucht beim nächsten Lauf neu auf
    zeile = speicher._db.execute("SELECT url FROM stand WHERE status IN ('BESTELLBAR', 'VORBESTELLBAR')").fetchone()
    assert zeile is not None
    speicher._db.execute("DELETE FROM stand WHERE url = ?", (zeile[0],))
    speicher._db.commit()
    lauf(e, speicher, {GTTG_LISTE: liste}, melder, minuten=20)   # Filter unverändert
    assert any("Neu im Shop entdeckt" in k.text for k in melder.nachrichten[-1]["kaesten"])
