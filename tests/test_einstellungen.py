"""Tests für das Laden von config.yaml."""

import pytest

from bot.einstellungen import ConfigFehler, lade_einstellungen
from bot.status import Status


def schreibe(tmp_path, inhalt: str):
    """Legt eine Test-config.yaml in einem Temp-Ordner an."""
    pfad = tmp_path / "config.yaml"
    pfad.write_text(inhalt, encoding="utf-8")
    return pfad


def test_echte_config_ist_gueltig():
    einstellungen = lade_einstellungen()
    assert einstellungen.allgemein.zeitzone == "Europe/Berlin"
    assert Status.BESTELLBAR in einstellungen.standard_regeln.ping_bei_status
    assert "mediamarkt.de" in einstellungen.vertrauenswuerdige_shops


def test_leere_datei_nutzt_standardwerte(tmp_path):
    einstellungen = lade_einstellungen(schreibe(tmp_path, ""))
    assert einstellungen.allgemein.min_minuten_pro_shop == 15
    assert einstellungen.standard_regeln.sprache == "egal"
    assert einstellungen.watchlist == []


def test_fehlende_datei(tmp_path):
    with pytest.raises(ConfigFehler, match="fehlt"):
        lade_einstellungen(tmp_path / "gibt-es-nicht.yaml")


def test_kaputtes_yaml_nennt_zeile(tmp_path):
    with pytest.raises(ConfigFehler, match="Zeile"):
        lade_einstellungen(schreibe(tmp_path, "allgemein:\n  zeitzone: [kaputt\n"))


def test_tippfehler_wird_erkannt(tmp_path):
    with pytest.raises(ConfigFehler, match="max_pries"):
        lade_einstellungen(schreibe(tmp_path, "standard_regeln:\n  max_pries: 100\n"))


def test_unbekannter_status(tmp_path):
    with pytest.raises(ConfigFehler, match="VERFUEGBAR"):
        lade_einstellungen(schreibe(tmp_path, "standard_regeln:\n  ping_bei_status: [VERFUEGBAR]\n"))


def test_status_klein_geschrieben_ist_ok(tmp_path):
    einstellungen = lade_einstellungen(
        schreibe(tmp_path, "standard_regeln:\n  ping_bei_status: [bestellbar]\n")
    )
    assert einstellungen.standard_regeln.ping_bei_status == [Status.BESTELLBAR]


@pytest.mark.parametrize("ruhezeit", ["22-6", "25:00-06:00", "22:00"])
def test_falsche_ruhezeit(tmp_path, ruhezeit):
    with pytest.raises(ConfigFehler, match="ruhezeit"):
        lade_einstellungen(schreibe(tmp_path, f'standard_regeln:\n  ruhezeit: "{ruhezeit}"\n'))


def test_richtige_ruhezeit(tmp_path):
    einstellungen = lade_einstellungen(
        schreibe(tmp_path, 'standard_regeln:\n  ruhezeit: "22:00-06:00"\n')
    )
    assert einstellungen.standard_regeln.ruhezeit == "22:00-06:00"


def test_max_preis_muss_zahl_sein(tmp_path):
    with pytest.raises(ConfigFehler, match="Zahl"):
        lade_einstellungen(schreibe(tmp_path, "standard_regeln:\n  max_preis: billig\n"))


def test_zu_haeufige_abfragen_verboten(tmp_path):
    # Höflichkeitsregel: höchstens alle 10 Minuten pro Shop
    with pytest.raises(ConfigFehler, match="mindestens 10"):
        lade_einstellungen(schreibe(tmp_path, "allgemein:\n  min_minuten_pro_shop: 2\n"))


def test_falsche_zeitzone(tmp_path):
    with pytest.raises(ConfigFehler, match="Zeitzone"):
        lade_einstellungen(schreibe(tmp_path, "allgemein:\n  zeitzone: Mars/Olympus\n"))


def test_sprache(tmp_path):
    einstellungen = lade_einstellungen(schreibe(tmp_path, "standard_regeln:\n  sprache: de\n"))
    assert einstellungen.standard_regeln.sprache == "DE"
    with pytest.raises(ConfigFehler, match="sprache"):
        lade_einstellungen(schreibe(tmp_path, "standard_regeln:\n  sprache: FR\n"))


def test_shops_werden_vereinheitlicht(tmp_path):
    einstellungen = lade_einstellungen(
        schreibe(tmp_path, "vertrauenswuerdige_shops:\n  - https://www.Mueller.de/\n")
    )
    assert einstellungen.vertrauenswuerdige_shops == ["mueller.de"]


def test_watchlist_mit_eigenen_regeln(tmp_path):
    einstellungen = lade_einstellungen(schreibe(tmp_path, """
standard_regeln:
  max_preis: 200
  ping_bei_status: [BESTELLBAR]
watchlist:
  - name: "Display"
    links:
      - https://www.gate-to-the-games.de/display
    max_preis: 150
  - name: "ETB"
    links:
      - https://www.card-corner.de/etb
"""))
    display, etb = einstellungen.watchlist
    assert display.links == ["https://www.gate-to-the-games.de/display"]
    assert display.regeln.max_preis == 150                      # eigene Regel
    assert display.regeln.ping_bei_status == [Status.BESTELLBAR]  # vom Standard geerbt
    assert etb.regeln.max_preis == 200


def test_watchlist_ohne_links_und_ohne_suche(tmp_path):
    with pytest.raises(ConfigFehler, match="suche"):
        lade_einstellungen(schreibe(tmp_path, "watchlist:\n  - name: X\n"))


def test_watchlist_mit_suchbegriffen(tmp_path):
    einstellungen = lade_einstellungen(schreibe(tmp_path, """
watchlist:
  - name: "Dunkelnacht"
    suche:
      - Dunkelnacht
      - Pitch Black
"""))
    produkt = einstellungen.watchlist[0]
    assert produkt.suche == ["Dunkelnacht", "Pitch Black"]
    assert produkt.links == []


def test_watchlist_link_muss_link_sein(tmp_path):
    with pytest.raises(ConfigFehler, match="kein Link"):
        lade_einstellungen(schreibe(tmp_path, "watchlist:\n  - name: X\n    links:\n      - www.shop.de\n"))


def test_watchlist_tippfehler_bei_regel(tmp_path):
    with pytest.raises(ConfigFehler, match="max_pries"):
        lade_einstellungen(schreibe(tmp_path, "watchlist:\n  - name: X\n    links: [https://a.de]\n    max_pries: 1\n"))


def test_kategorien_und_filter(tmp_path):
    einstellungen = lade_einstellungen(schreibe(tmp_path, """
kategorien:
  - name: "Vorverkauf"
    link: https://www.gate-to-the-games.de/liste/
kategorie_filter:
  nur_mit: [Display, ETB]
  ohne: [Koreanisch]
"""))
    assert einstellungen.kategorien[0].link == "https://www.gate-to-the-games.de/liste/"
    assert einstellungen.kategorie_filter.nur_mit == ["Display", "ETB"]
    assert einstellungen.kategorie_filter.ohne == ["Koreanisch"]


def test_echte_config_hat_watchlist_und_kategorien():
    einstellungen = lade_einstellungen()
    assert einstellungen.watchlist and einstellungen.kategorien
    sets = {p.name for p in einstellungen.watchlist}
    assert {"Dunkelnacht", "Fatale Flammen", "Optimale Ordnung"} <= sets
    assert all(p.suche for p in einstellungen.watchlist)
