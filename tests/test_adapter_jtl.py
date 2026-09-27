"""Tests der Status-Erkennung mit echten, gespeicherten Shop-Seiten.

Wenn ein Shop sein Layout ändert, schlagen diese Tests fehl. Dann neue
Beispielseiten holen (tests/beispiele/verkleinern.py) und den Adapter anpassen.
"""

from datetime import date
from pathlib import Path

import pytest

from bot.adapter import NICHT_ERLAUBT, adapter_fuer
from bot.adapter.basis import datum_aus_text, preis_als_zahl, schema_status
from bot.status import Status
from tests.hilfen import ohne_ausverkauft_markierung

BEISPIELE = Path(__file__).parent / "beispiele"
HEUTE = date(2026, 9, 26)  # Tag, an dem die Beispielseiten gespeichert wurden
GTTG = "https://www.gate-to-the-games.de/produkt"
CC = "https://www.card-corner.de/produkt"


def lies(name: str) -> str:
    return (BEISPIELE / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "datei, url, status, preis, extra",
    [
        # Ausverkaufte Vorbestellung: „Verfügbar ab …“ + schema.org PreOrder, aber Banner „Ausverkauft“
        ("gate_to_the_games/produkt_vorbestellung_ausverkauft.html", GTTG, Status.AUSVERKAUFT, 199.90,
         {"liefertermin": None}),
        ("gate_to_the_games/produkt_ausverkauft.html", GTTG, Status.AUSVERKAUFT, 7.99, {}),
        ("gate_to_the_games/produkt_bestellbar_mengenlimit.html", GTTG, Status.BESTELLBAR, 229.95,
         {"mengenlimit": 1}),
        ("gate_to_the_games/produkt_knapper_bestand.html", GTTG, Status.BESTELLBAR, 279.90, {}),
        ("card_corner/produkt_bestellbar.html", CC, Status.BESTELLBAR, 74.99, {}),
        # Auf dieser Seite steht in den Empfehlungen ein Vorbestell-Produkt – das darf nicht zählen
        ("card_corner/produkt_wenig_auf_lager.html", CC, Status.BESTELLBAR, 599.99, {}),
        # schema.org PreOrder, aber rote Ampel „Ausverkauft – Benachrichtigen wenn verfügbar“
        ("card_corner/produkt_vorbestellung_ausverkauft.html", CC, Status.AUSVERKAUFT, None, {}),
    ],
)
def test_produktseiten(datei, url, status, preis, extra):
    ergebnis = adapter_fuer(url).erkenne_produkt(lies(datei), url, HEUTE)
    assert ergebnis.status == status
    assert ergebnis.preis == preis
    assert ergebnis.verkaeufer == "Shop"
    assert ergebnis.titel
    for feld, wert in extra.items():
        assert getattr(ergebnis, feld) == wert


def test_echte_vorbestellung_ohne_ausverkauft_banner():
    html = ohne_ausverkauft_markierung(lies("gate_to_the_games/produkt_vorbestellung_ausverkauft.html"))
    ergebnis = adapter_fuer(GTTG).erkenne_produkt(html, GTTG, HEUTE)
    assert ergebnis.status == Status.VORBESTELLBAR
    assert ergebnis.liefertermin == "06.11.2026"
    assert ergebnis.preis == 199.90


def test_liste_gate_to_the_games():
    url = "https://www.gate-to-the-games.de/Pokemon-Karten/Pokemon-Sammelkarten/"
    liste = adapter_fuer(url).erkenne_liste(lies("gate_to_the_games/liste_vorverkauf.html"), url, HEUTE)
    assert len(liste) == 25
    nach_url = {e.url: e.ergebnis for e in liste}
    display = nach_url["https://www.gate-to-the-games.de/Pokemon-Mega-Entwicklung-Delta-Herrschaft-Display-36-Booster-deutsch"]
    # Steht dort mit „Verfügbar ab: 06.11.2026“, ist aber als „Ausverkauft“ markiert
    assert display.status == Status.AUSVERKAUFT
    assert display.preis == 199.90
    assert "Display" in display.titel
    # Zum Zeitpunkt der Aufnahme war im Vorverkauf alles ausverkauft
    assert {e.ergebnis.status for e in liste} == {Status.AUSVERKAUFT}
    booster = nach_url["https://www.gate-to-the-games.de/Pokemon-30-Jahre-Booster-deutsch"]
    assert booster.status == Status.AUSVERKAUFT
    # Keine Links mit '#tab-votes' und keine Dubletten
    assert all("#" not in e.url for e in liste)


def test_liste_card_corner():
    url = "https://www.card-corner.de/Pokemon-Display"
    liste = adapter_fuer(url).erkenne_liste(lies("card_corner/liste_displays.html"), url, HEUTE)
    assert len(liste) == 24
    assert all(e.ergebnis.status != Status.UNBEKANNT for e in liste)
    gem = next(e for e in liste if e.url.endswith("Pokemon-Gem-Pack-6-Display-CBB6C"))
    assert gem.ergebnis.status == Status.BESTELLBAR
    assert gem.ergebnis.preis == 33.99


def test_liste_card_corner_ausverkaufte_vorbestellungen():
    url = "https://www.card-corner.de/Neu-Eingetroffen"
    liste = adapter_fuer(url).erkenne_liste(lies("card_corner/liste_neu_eingetroffen.html"), url, HEUTE)
    # Diese beiden stehen mit schema.org „PreOrder“ in der Liste, sind aber als „Ausverkauft“ markiert
    koreanisch = [e for e in liste if "30th-Celebration" in e.url and "Koreanisch" in e.url]
    assert len(koreanisch) == 2
    assert all(e.ergebnis.status == Status.AUSVERKAUFT for e in koreanisch)
    # Preis steht noch nicht fest (0 €) → kein Preis statt 0 €
    assert all(e.ergebnis.preis is None for e in koreanisch)
    assert not any(e.ergebnis.status == Status.VORBESTELLBAR for e in liste)


def test_liste_vorbestellung_ohne_ausverkauft_banner():
    url = "https://www.gate-to-the-games.de/Pokemon-Karten/Pokemon-Sammelkarten/"
    html = ohne_ausverkauft_markierung(lies("gate_to_the_games/liste_vorverkauf.html"))
    liste = adapter_fuer(url).erkenne_liste(html, url, HEUTE)
    display = next(e.ergebnis for e in liste if "Delta-Herrschaft-Display" in e.url)
    assert display.status == Status.VORBESTELLBAR
    assert display.liefertermin == "06.11.2026"


def test_seite_ohne_produktdaten_ist_unbekannt():
    ergebnis = adapter_fuer(GTTG).erkenne_produkt("<html><body>Wartungsarbeiten</body></html>", GTTG, HEUTE)
    assert ergebnis.status == Status.UNBEKANNT
    assert ergebnis.hinweis


def test_unbekannter_shop_hat_keinen_adapter():
    assert adapter_fuer("https://www.beispiel-shop.de/produkt") is None
    assert "netto-online.de" in NICHT_ERLAUBT


@pytest.mark.parametrize(
    "text, zahl",
    [("199.90", 199.90), ("199,90 €", 199.90), ("1.234,56 €", 1234.56), ("ab 5 €", 5.0), ("0", None), ("", None),
     (None, None)],
)
def test_preis_als_zahl(text, zahl):
    assert preis_als_zahl(text) == zahl


def test_datum_und_schema():
    assert datum_aus_text("Verfügbar ab: 06.11.2026") == date(2026, 11, 6)
    assert datum_aus_text("kein Datum") is None
    assert schema_status("https://schema.org/PreOrder") == Status.VORBESTELLBAR
    assert schema_status("http://schema.org/InStock") == Status.BESTELLBAR
    assert schema_status("https://schema.org/SoldOut") == Status.AUSVERKAUFT
    assert schema_status("https://schema.org/Irgendwas") is None


def test_such_adressen():
    gttg = adapter_fuer(GTTG)
    cc = adapter_fuer(CC)
    assert gttg.such_url("Fatale Flammen") == "https://www.gate-to-the-games.de/?suche=Fatale+Flammen&af=100"
    assert gttg.such_url("Fatale Flammen", 2) == "https://www.gate-to-the-games.de/?suche=Fatale+Flammen&af=100&seite=2"
    assert cc.such_url("Pitch Black") == "https://www.card-corner.de/?suche=Pitch+Black&af=50"


def test_suchergebnisse_gate_to_the_games():
    url = adapter_fuer(GTTG).such_url("Fatale Flammen")
    liste = adapter_fuer(GTTG).erkenne_liste(lies("gate_to_the_games/suche_fatale_flammen.html"), url, HEUTE)
    assert len(liste) == 100  # volle Seite → der Bot holt auch Seite 2
    nach_titel = {e.ergebnis.titel: e.ergebnis for e in liste}
    display = nach_titel["Mega-Entwicklung Fatale Flammen Display (36 Booster) (deutsch)"]
    assert display.status == Status.BESTELLBAR and display.preis == 399.90
    assert nach_titel["Mega-Entwicklung Fatale Flammen Booster Bundle (deutsch)"].status == Status.AUSVERKAUFT


def test_banner_auf_lager_wenn_die_lieferampel_fehlt():
    url = "https://www.card-corner.de/pokemon-optimale-ordnung"
    liste = adapter_fuer(url).erkenne_liste(lies("card_corner/liste_set_optimale_ordnung.html"), url, HEUTE)
    nihil = next(e.ergebnis for e in liste if e.ergebnis.titel == "Pokemon Nihil Zero (M3) Display")
    assert nihil.status == Status.BESTELLBAR
