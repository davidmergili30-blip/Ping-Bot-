"""Tests für die Steuerung über die GitHub-App (Run workflow → Aktion)."""

import shutil
from pathlib import Path

import pytest

from bot import __main__ as start
from bot import discord as discord_modul
from bot.adapter.basis import CheckErgebnis
from bot.einstellungen import lade_einstellungen
from bot.speicher import Speicher
from bot.status import Status
from bot.steuerung import SteuerFehler, preis_aus_eingabe

ECHTE_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"
WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/abcDEF"


class FalscheAntwort:
    status_code = 204


@pytest.fixture
def umgebung(monkeypatch, tmp_path):
    """Kopie der echten config.yaml, eigene Datenbank, Discord-Attrappe."""
    config = tmp_path / "config.yaml"
    shutil.copy(ECHTE_CONFIG, config)
    monkeypatch.setenv("BOT_CONFIG", str(config))
    monkeypatch.setenv("BOT_DATENBANK", str(tmp_path / "bot.db"))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    gesendet = []
    monkeypatch.setattr(discord_modul.requests, "post",
                        lambda url, json, params, timeout: gesendet.append(json) or FalscheAntwort())
    return {"config": config, "gesendet": gesendet, "db": tmp_path / "bot.db"}


def titel(umgebung):
    return [k["title"] for n in umgebung["gesendet"] for k in n["embeds"]]


def test_set_hinzufuegen(umgebung):
    code = start.main(["set-hinzufuegen", "--name", "Stellarkrone", "--suchbegriffe", "Stellar Crown, Stella Miracle"])
    assert code == 0
    produkt = lade_einstellungen(umgebung["config"]).watchlist[0]
    assert produkt.name == "Stellarkrone"
    assert produkt.suche == ["Stellarkrone", "Stellar Crown", "Stella Miracle"]
    assert titel(umgebung) == ["✅ Set hinzugefügt: Stellarkrone"]


def test_kommentare_bleiben_erhalten(umgebung):
    vorher = umgebung["config"].read_text(encoding="utf-8")
    start.main(["max-preis", "--name", "Dunkelnacht", "--preis", "180"])
    nachher = umgebung["config"].read_text(encoding="utf-8")
    assert "# Ehrlicher User-Agent" in nachher
    assert "# japanisch (sehr wahrscheinlich dasselbe Set)" in nachher
    # Nur die neue Zeile ist dazugekommen, sonst ist alles gleich
    neue_zeilen = [z for z in nachher.splitlines() if z not in vorher.splitlines()]
    assert neue_zeilen == ["    max_preis: 180"]


def test_max_preis_setzen_und_aufheben(umgebung):
    assert start.main(["max-preis", "--name", "fatale flammen", "--preis", "199,90"]) == 0
    fatale = next(p for p in lade_einstellungen(umgebung["config"]).watchlist if p.name == "Fatale Flammen")
    assert fatale.regeln.max_preis == 199.90
    assert start.main(["max-preis", "--name", "Fatale Flammen", "--preis", "aus"]) == 0
    fatale = next(p for p in lade_einstellungen(umgebung["config"]).watchlist if p.name == "Fatale Flammen")
    assert fatale.regeln.max_preis is None
    assert titel(umgebung) == ["💶 Maximalpreis für Fatale Flammen: 199,90 €",
                               "💶 Maximalpreis aufgehoben: Fatale Flammen"]


def test_set_ueber_suchbegriff_finden(umgebung):
    # „Pitch Black“ ist ein Suchbegriff des Sets „Dunkelnacht“
    assert start.main(["max-preis", "--name", "Pitch Black", "--preis", "150"]) == 0
    dunkel = next(p for p in lade_einstellungen(umgebung["config"]).watchlist if p.name == "Dunkelnacht")
    assert dunkel.regeln.max_preis == 150


def test_unbekanntes_set_meldet_fehler_und_aendert_nichts(umgebung):
    vorher = umgebung["config"].read_text(encoding="utf-8")
    assert start.main(["set-entfernen", "--name", "Gibt es nicht"]) == 1
    assert umgebung["config"].read_text(encoding="utf-8") == vorher
    assert titel(umgebung) == ["❌ set-entfernen hat nicht geklappt"]
    assert "Vorhanden:" in umgebung["gesendet"][0]["embeds"][0]["description"]


def test_set_entfernen(umgebung):
    assert start.main(["set-entfernen", "--name", "30 Jahre"]) == 0
    namen = [p.name for p in lade_einstellungen(umgebung["config"]).watchlist]
    assert "30 Jahre" not in namen and "Dunkelnacht" in namen


def test_doppeltes_set_wird_abgelehnt(umgebung):
    assert start.main(["set-hinzufuegen", "--name", "dunkelnacht"]) == 1


def test_pause_und_weiter(umgebung, monkeypatch):
    assert start.main(["pause"]) == 0
    assert lade_einstellungen(umgebung["config"]).allgemein.pausiert is True
    # Pausiert: Der normale Lauf fragt gar nichts ab
    monkeypatch.setattr(start, "Abrufer", lambda *a, **k: pytest.fail("darf im Pause-Modus nichts abrufen"))
    assert start.main(["normaler-lauf"]) == 0
    assert start.main(["weiter"]) == 0
    assert lade_einstellungen(umgebung["config"]).allgemein.pausiert is False
    assert titel(umgebung) == ["⏸️ Bot pausiert", "▶️ Bot läuft wieder"]


def test_watchlist_anzeigen(umgebung):
    start.main(["max-preis", "--name", "Dunkelnacht", "--preis", "180"])
    umgebung["gesendet"].clear()
    assert start.main(["watchlist"]) == 0
    text = umgebung["gesendet"][0]["embeds"][0]["description"]
    assert "**Dunkelnacht** – Suche: Dunkelnacht, Pitch Black, Abyss Eye · Maximalpreis: ganzes Set 180,00 €" in text
    assert "**Fatale Flammen**" in text and "kein Maximalpreis" in text


def test_status_zeigt_verfuegbare_produkte(umgebung):
    speicher = Speicher(umgebung["db"])
    speicher.setze_stand("https://shop.de/a", "Card-Corner", "Pitch Black ETB", Status.BESTELLBAR, 79.99)
    speicher.setze_stand("https://shop.de/b", "Card-Corner", "Dunkelnacht Display", Status.AUSVERKAUFT, 194.99)
    speicher.setze_blockade("beispiel.de", "Seite blockt den Bot (HTTP 403)")
    speicher.setze_meta("letzter_lauf", "2026-09-27T20:00:00+00:00")
    speicher.schliessen()
    assert start.main(["status"]) == 0
    text = umgebung["gesendet"][0]["embeds"][0]["description"]
    assert "Letzter Lauf: 27.09.2026 um 22:00 Uhr" in text
    assert "[Pitch Black ETB](https://shop.de/a) – 79,99 € (Card-Corner)" in text
    assert "Dunkelnacht Display" not in text  # ausverkauft
    assert "beispiel.de" in text


@pytest.mark.parametrize("eingabe, preis", [("180", 180.0), ("179,90", 179.9), ("180 €", 180.0),
                                            ("1.234,50", 1234.5), ("aus", None), ("", None), ("0", None)])
def test_preis_aus_eingabe(eingabe, preis):
    assert preis_aus_eingabe(eingabe) == preis


def test_preis_unsinn():
    with pytest.raises(SteuerFehler, match="kein Preis"):
        preis_aus_eingabe("billig")


def test_max_preis_wirkt_auf_pings():
    from bot.einstellungen import Regeln
    from bot.pings import ping_grund
    regeln = Regeln(ping_bei_status=[Status.BESTELLBAR], max_preis=180)
    assert ping_grund(None, CheckErgebnis(Status.BESTELLBAR, 199.9), regeln, True) is None
    assert ping_grund(None, CheckErgebnis(Status.BESTELLBAR, 179.9), regeln, True) == "neu"


def test_neues_set_und_preis_landen_an_der_richtigen_stelle(umgebung):
    start.main(["set-hinzufuegen", "--name", "Stellarkrone"])
    start.main(["max-preis", "--name", "Dunkelnacht", "--preis", "180"])
    zeilen = umgebung["config"].read_text(encoding="utf-8").splitlines()
    # Neues Set direkt unter „watchlist:“ – nicht unter dem Kommentar der Kategorien
    watch = zeilen.index("watchlist:")
    assert zeilen[watch + 1] == "  - name: Stellarkrone"
    # Maximalpreis direkt unter dem Set-Namen
    dunkel = zeilen.index('  - name: "Dunkelnacht"')
    assert zeilen[dunkel + 1] == "    max_preis: 180"


def test_set_in_leere_watchlist(umgebung):
    umgebung["config"].write_text("watchlist: []\n", encoding="utf-8")
    assert start.main(["set-hinzufuegen", "--name", "Dunkelnacht", "--suchbegriffe", "Pitch Black"]) == 0
    text = umgebung["config"].read_text(encoding="utf-8")
    assert "  - name: Dunkelnacht\n    suche:\n      - Dunkelnacht\n      - Pitch Black" in text


def test_pause_aendert_nur_eine_zeile(umgebung):
    vorher = umgebung["config"].read_text(encoding="utf-8").splitlines()
    start.main(["pause"])
    nachher = umgebung["config"].read_text(encoding="utf-8").splitlines()
    assert [z for z in nachher if z not in vorher] == ["  pausiert: true"]
    assert len(nachher) == len(vorher)


# --- Maximalpreis je Produktart ------------------------------------------------------------

def test_max_preis_je_produktart(umgebung):
    assert start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "Display", "--preis", "180"]) == 0
    assert start.main(["max-preis", "--name", "Pitch Black", "--produkt", "ttb", "--preis", "59,99"]) == 0
    dunkel = next(p for p in lade_einstellungen(umgebung["config"]).watchlist if p.name == "Dunkelnacht")
    assert dunkel.preise == {"Display": 180, "Top-Trainer-Box": 59.99}
    assert dunkel.regeln.max_preis is None                     # das ganze Set bleibt ohne Grenze
    assert titel(umgebung)[-1] == "💶 Maximalpreis für Dunkelnacht – Top-Trainer-Box: 59,99 €"
    # Direkt unter dem Set-Namen, sauber eingerückt
    zeilen = umgebung["config"].read_text(encoding="utf-8").splitlines()
    i = zeilen.index('  - name: "Dunkelnacht"')
    assert zeilen[i + 1:i + 4] == ["    preise:", "      Display: 180", "      Top-Trainer-Box: 59.99"]


def test_max_preis_je_produktart_und_ganzes_set(umgebung):
    start.main(["max-preis", "--name", "Dunkelnacht", "--preis", "250"])
    start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "Mini-Tin", "--preis", "15"])
    zeilen = umgebung["config"].read_text(encoding="utf-8").splitlines()
    i = zeilen.index('  - name: "Dunkelnacht"')
    assert zeilen[i + 1:i + 4] == ["    max_preis: 250", "    preise:", "      Mini-Tin: 15"]
    text = umgebung["gesendet"][-1]["embeds"][0]["description"]
    assert "Alle Preise dieses Sets: Maximalpreis: ganzes Set 250,00 € · Mini-Tin 15,00 €" in text


def test_max_preis_je_produktart_aufheben(umgebung):
    vorher = umgebung["config"].read_text(encoding="utf-8")
    start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "Display", "--preis", "180"])
    start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "Display", "--preis", "aus"])
    assert umgebung["config"].read_text(encoding="utf-8") == vorher   # alles wieder wie vorher
    assert titel(umgebung)[-1] == "💶 Maximalpreis aufgehoben: Dunkelnacht – Display"


def test_unbekannte_produktart(umgebung):
    vorher = umgebung["config"].read_text(encoding="utf-8")
    assert start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "Booster", "--preis", "5"]) == 1
    assert umgebung["config"].read_text(encoding="utf-8") == vorher
    assert titel(umgebung) == ["❌ max-preis hat nicht geklappt"]


def test_ganzes_set_aus_der_app(umgebung):
    # Die App schickt „ganzes Set“, wenn nichts ausgewählt wurde
    assert start.main(["max-preis", "--name", "Dunkelnacht", "--produkt", "ganzes Set", "--preis", "200"]) == 0
    dunkel = next(p for p in lade_einstellungen(umgebung["config"]).watchlist if p.name == "Dunkelnacht")
    assert dunkel.regeln.max_preis == 200 and dunkel.preise == {}


def test_preise_in_config_werden_geprueft(tmp_path):
    from bot.einstellungen import ConfigFehler
    config = tmp_path / "config.yaml"
    config.write_text("watchlist:\n  - name: X\n    suche: [X]\n    preise:\n      Booster: 5\n", encoding="utf-8")
    with pytest.raises(ConfigFehler, match="Unbekannte Produktart 'Booster'"):
        lade_einstellungen(config)
    config.write_text("watchlist:\n  - name: X\n    suche: [X]\n    preise:\n      ETB: billig\n", encoding="utf-8")
    with pytest.raises(ConfigFehler, match="muss eine Zahl sein"):
        lade_einstellungen(config)
