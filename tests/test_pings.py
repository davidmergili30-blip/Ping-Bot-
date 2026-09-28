"""Tests für die Entscheidung „Ping oder nicht?“ und das Aussehen der Pings."""

import pytest

from bot.adapter.basis import CheckErgebnis
from bot.einstellungen import Regeln
from bot.pings import euro, ping_grund, ping_kasten
from bot.status import Status

B, V, A = Status.BESTELLBAR, Status.VORBESTELLBAR, Status.AUSVERKAUFT
STANDARD = Regeln(ping_bei_status=[B, V, Status.NUR_EINLADUNG])


@pytest.mark.parametrize(
    "alt, neu, regeln, grund",
    [
        (None, CheckErgebnis(V, 199.9), STANDARD, "neu"),
        (None, CheckErgebnis(A, 199.9), STANDARD, None),                 # AUSVERKAUFT pingt nicht
        ((A, 199.9), CheckErgebnis(B, 199.9), STANDARD, "status"),
        ((B, 199.9), CheckErgebnis(B, 199.9), STANDARD, None),           # nichts geändert
        ((B, 200.0), CheckErgebnis(B, 179.0), STANDARD, "preissturz"),   # −10,5 %
        ((B, 200.0), CheckErgebnis(B, 185.0), STANDARD, None),           # nur −7,5 %
        ((B, 200.0), CheckErgebnis(Status.UNBEKANNT), STANDARD, None),   # nie bei UNBEKANNT
        (None, CheckErgebnis(B, 199.9), Regeln(ping_bei_status=[B], max_preis=150), None),
        ((B, 155.0), CheckErgebnis(B, 149.0), Regeln(ping_bei_status=[B], max_preis=150), "unter_maximalpreis"),
        (None, CheckErgebnis(Status.NUR_MARKTPLATZ, 99.0), Regeln(ping_bei_status=[Status.NUR_MARKTPLATZ]), None),
        (None, CheckErgebnis(Status.NUR_MARKTPLATZ, 99.0),
         Regeln(ping_bei_status=[Status.NUR_MARKTPLATZ], marktplatz_angebote=True), "neu"),
    ],
)
def test_ping_grund(alt, neu, regeln, grund):
    assert ping_grund(alt, neu, regeln, shop_vertraut=True) == grund


def test_nur_vertrauenswuerdige_shops():
    regeln = Regeln(ping_bei_status=[B], nur_vertrauenswuerdige_shops=True)
    assert ping_grund(None, CheckErgebnis(B, 10.0), regeln, shop_vertraut=False) is None
    assert ping_grund(None, CheckErgebnis(B, 10.0), regeln, shop_vertraut=True) == "neu"


def test_ping_kasten_wie_im_beispiel():
    kasten = ping_kasten(
        "Display „Set XY“ (DE)", "Gate to the Games", "https://shop.de/x",
        CheckErgebnis(B, 144.99, verkaeufer="Shop", mengenlimit=1), alt=(A, 144.99), grund="status",
        shop_vertraut=True,
    )
    assert kasten.titel == "🟢 BESTELLBAR – Display „Set XY“ (DE)"
    assert "**Gate to the Games** · 144,99 € (Verkauf durch Shop)" in kasten.text
    assert "Vorher: AUSVERKAUFT" in kasten.text
    assert "Max. 1 Stück" in kasten.text
    assert kasten.link == "https://shop.de/x"
    assert "⚠️" not in kasten.text


def test_unbekannter_shop_bekommt_warnung():
    kasten = ping_kasten("X", "Irgendwo", "https://x.de", CheckErgebnis(B, 5.0), None, "neu", shop_vertraut=False)
    assert "⚠️ Shop ist nicht auf deiner Vertrauensliste" in kasten.text


def test_preissturz_zeigt_alten_preis():
    kasten = ping_kasten("X", "Shop", "https://x.de", CheckErgebnis(B, 150.0), (B, 200.0), "preissturz", True)
    assert kasten.titel.startswith("📉 PREISSTURZ")
    assert "Vorher: 200,00 € (−25 %)" in kasten.text


def test_euro():
    assert euro(1234.5) == "1.234,50 €"
    assert euro(None) == "Preis noch offen"


# --- Getrennte Nachrichten: kaufbar / Einladung / Info -------------------------------------

def test_nachrichten_nach_art_getrennt():
    from bot.discord import Kasten
    from bot.pings import nach_art

    kaesten = [
        Kasten("📋 Neu überwacht: Liste"),                          # info (Standard)
        Kasten("🟡 NUR AUF EINLADUNG – ETB", art="einladung"),
        Kasten("🟢 BESTELLBAR – Display", art="kaufbar"),
        Kasten("🔵 VORBESTELLBAR – Bundle", art="kaufbar"),
        Kasten("Komisch", art="gibt-es-nicht"),                      # Unbekanntes landet bei den Infos
    ]
    nachrichten = nach_art(kaesten)
    assert [text for text, _ in nachrichten] == [
        "🛒 JETZT KAUFBAR – 🟢 BESTELLBAR – Display (+1 weitere)",
        "🟡 NUR AUF EINLADUNG – 🟡 NUR AUF EINLADUNG – ETB",
        "ℹ️ Übersicht & Hinweise – 📋 Neu überwacht: Liste (+1 weitere)",
    ]
    assert sum(len(k) for _, k in nachrichten) == len(kaesten)  # nichts geht verloren
    assert nach_art([]) == []


@pytest.mark.parametrize("status, art", [
    (Status.BESTELLBAR, "kaufbar"), (Status.VORBESTELLBAR, "kaufbar"), (Status.NUR_MARKTPLATZ, "kaufbar"),
    (Status.NUR_EINLADUNG, "einladung"), (Status.BALD, "info"), (Status.NUR_FILIALE, "info"),
])
def test_ping_kasten_bekommt_richtige_art(status, art):
    kasten = ping_kasten("X", "Shop", "https://x.de/p", CheckErgebnis(status, preis=10.0), None, "neu", True)
    assert kasten.art == art


def test_link_mit_eckigen_klammern_bleibt_antippbar():
    from bot.pings import als_link
    assert als_link("[Amazon] Top Trainer Box [Prime]", "https://x.de/d") == "[(Amazon) Top Trainer Box (Prime)](https://x.de/d)"
    assert als_link(None, "https://x.de/d") == "[Produkt](https://x.de/d)"
