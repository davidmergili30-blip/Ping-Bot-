"""Tests für TCGCHECK (günstigster Preis über 200+ Shops) und Shopify-Shops – mit echten, gekürzten Daten."""

from pathlib import Path

from bot.adapter import adapter_fuer
from bot.einstellungen import KategorieFilter
from bot.status import Status
from tests.test_lauf import FalscherMelder, einstellungen, lauf

BEISPIELE = Path(__file__).parent / "beispiele"
TCG_DE = "https://www.tcgcheck.de/pokemon/set/de/dunkelnacht/index"
TCG_JP = "https://www.tcgcheck.de/pokemon/set/jp/abyss-eye/index"
TCG_DISPLAY = "https://www.tcgcheck.de/pokemon/set/de/dunkelnacht/dunkelnacht-display"
TCG_TTB = "https://www.tcgcheck.de/pokemon/set/de/dunkelnacht/dunkelnacht-top-trainer-box"
CK = "https://www.card-knights.de/collections/pokemon-me05-dunkelnacht"
CC_RELEASE = "https://cardcosmos.de/collections/pokemon-release-kalender-2026"
CC_POKEMON = "https://cardcosmos.de/collections/pokemon-karten-kaufen"
PM_BALD = "https://www.play-maniac.de/collections/bald-im-shop"
PM_POKEMON = "https://www.play-maniac.de/collections/alle-pokemon-artikel"


def lies(name):
    return (BEISPIELE / name).read_text(encoding="utf-8")


def liste(url, datei):
    return {e.url: e.ergebnis for e in adapter_fuer(url).erkenne_liste(lies(datei), url)}


# --- TCGCHECK -----------------------------------------------------------------------------

def test_tcgcheck_set_uebersicht():
    produkte = liste(TCG_DE, "tcgcheck/set_dunkelnacht_de.html")
    display = produkte[TCG_DISPLAY]
    assert display.status == Status.BESTELLBAR
    assert (display.preis, display.uvp) == (184.90, 179.99)
    assert display.titel == "Dunkelnacht Display (DE)"          # Sprache aus der Adresse
    assert "Günstigster Preis über alle Shops" in display.info
    ttb = produkte[TCG_TTB]
    assert (ttb.preis, ttb.uvp) == (49.99, 59.99)
    # „Keine Angebote“ = nirgends zu haben
    case = produkte["https://www.tcgcheck.de/pokemon/set/de/dunkelnacht/dunkelnacht-booster-box-case"]
    assert case.status == Status.AUSVERKAUFT and case.preis is None and case.uvp == 1079.94
    assert len(produkte) == 10


def test_tcgcheck_japanisch():
    produkte = liste(TCG_JP, "tcgcheck/set_abyss_eye_jp.html")
    display = next(e for e in produkte.values() if "Display" in e.titel)
    assert display.titel == "Abyss Eye Display (JP)"
    assert display.preis == 69.99


def test_tcgcheck_produktseite():
    a = adapter_fuer(TCG_DISPLAY)
    e = a.erkenne_produkt(lies("tcgcheck/produkt_dunkelnacht_display.html"), TCG_DISPLAY)
    assert (e.status, e.preis, e.uvp, e.titel) == (Status.BESTELLBAR, 184.90, 179.99, "Dunkelnacht Display (DE)")


# --- Shopify ------------------------------------------------------------------------------

def test_shopify_adressen():
    a = adapter_fuer(CK)
    assert a.name == "Card-Knights"
    assert a.abruf_url(CK) == CK + "/products.json?limit=250"
    assert a.abruf_url(CK + "?page=2") == CK + "/products.json?limit=250&page=2"
    assert a.naechste_seite(CK, 250) == CK + "?page=2"
    assert a.naechste_seite(CK + "?page=2", 250) == CK + "?page=3"
    assert a.naechste_seite(CK, 17) is None                    # letzte Seite
    assert a.naechste_seite(CK + "?page=4", 250) is None       # höchstens 4 Seiten
    produkt = "https://www.card-knights.de/products/pokemon-me05-dunkelnacht-top-trainer-box-de"
    assert a.abruf_url(produkt) == produkt + ".js"


def test_shopify_ausverkauft():
    produkte = liste(CK, "shopify/cardknights_dunkelnacht.json")
    ttb = produkte["https://www.card-knights.de/products/pokemon-me05-dunkelnacht-top-trainer-box-de"]
    assert (ttb.status, ttb.preis, ttb.titel) == (Status.AUSVERKAUFT, 60.0, "Pokémon ME05 Dunkelnacht Top-Trainer-Box (DE)")
    assert all(e.status == Status.AUSVERKAUFT for e in produkte.values())


def test_shopify_vorbestell_abteilung():
    produkte = liste(CC_RELEASE, "shopify/cardcosmos_release_kalender.json")
    verfuegbar = [e for e in produkte.values() if e.status != Status.AUSVERKAUFT]
    assert verfuegbar and all(e.status == Status.VORBESTELLBAR for e in verfuegbar)


def test_shopify_art_aus_schlagwoertern():
    produkte = liste(CC_POKEMON, "shopify/cardcosmos_pokemon.json")
    titel = [e.titel for e in produkte.values()]
    # „Pokémon - Mega Evolution: Phantasmal Flames - EN“ nennt die Art nicht – das Schlagwort „Display“ schon
    assert "Pokémon - Mega Evolution: Phantasmal Flames - EN (Display)" in titel
    assert all(e.status in (Status.BESTELLBAR, Status.AUSVERKAUFT) for e in produkte.values())


def test_shopify_produktseite_js():
    a = adapter_fuer(CK)
    js = '{"title": "Pokémon ME05 Dunkelnacht Booster Display (DE)", "tags": [], "variants": [{"price": 17999, "available": true}]}'
    e = a.erkenne_produkt(js, "https://www.card-knights.de/products/x")
    assert (e.status, e.preis) == (Status.BESTELLBAR, 179.99)


def test_shopify_gemischte_vorverkaufsliste_nur_pokemon(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("Play-Maniac Vorverkauf", PM_BALD)], filter_=KategorieFilter(nur_mit=["Display"]))
    lauf(e, speicher, {PM_BALD + "/products.json?limit=250": lies("shopify/playmaniac_bald_im_shop.json")}, melder)
    text = " ".join(k.text for n in melder.nachrichten for k in n["kaesten"])
    assert "Hololive" not in text and "Godzilla" not in text


def test_shopify_schutzhuellen_werden_mit_filter_aussortiert(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("PM Pokémon", PM_POKEMON)],
                      filter_=KategorieFilter(nur_mit=["Display", "Kollektion", "Collection"],
                                              ohne=["Acryl", "Case", "Schutzhülle", "Chinesisch"]))
    lauf(e, speicher, {PM_POKEMON + "/products.json?limit=250": lies("shopify/playmaniac_pokemon.json")}, melder)
    text = " ".join(k.text for n in melder.nachrichten for k in n["kaesten"])
    assert "Acryl" not in text
    assert "Shrouded Fable Mini Tin Display" in text


# --- TCGCHECK im Lauf: UVP als Chase-Grenze -----------------------------------------------

def _mit_ttb_preis(preis: str) -> str:
    html = lies("tcgcheck/set_dunkelnacht_de.html")
    return html.replace('<meta content="49.99" itemprop="price"/>', f'<meta content="{preis}" itemprop="price"/>')


def test_tcgcheck_zur_uvp(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("TCGCHECK Dunkelnacht", TCG_DE)], suche=[("Dunkelnacht", ["Dunkelnacht"])],
                      filter_=KategorieFilter(nur_mit=["Display", "Top Trainer"], ohne=["Case"]))
    leer = "<html></html>"
    such = {"https://www.gate-to-the-games.de/?suche=Dunkelnacht&af=100": leer,
            "https://www.card-corner.de/?suche=Dunkelnacht&af=50": leer}
    teuer = _mit_ttb_preis("64.99")
    assert teuer != lies("tcgcheck/set_dunkelnacht_de.html")
    # 1. Lauf: Übersicht, kein Einzel-Ping (die TTB ist gerade über der UVP)
    lauf(e, speicher, {TCG_DE: teuer, **such}, melder)
    assert not any(k.art == "chase" for n in melder.nachrichten for k in n["kaesten"])
    # 2. Lauf: TTB fällt auf 49,99 € (UVP 59,99 €) → 🚨 ZUR UVP
    lauf(e, speicher, {TCG_DE: _mit_ttb_preis("49.99"), **such}, melder, minuten=20)
    chase = [k for k in melder.nachrichten[-1]["kaesten"] if k.art == "chase"]
    assert [k.titel for k in chase] == ["🚨 ZUR UVP – Dunkelnacht Top Trainer Box (DE)"]
    assert "🚨 **49,99 € – zur UVP (59,99 €) oder günstiger!** 🚨" in chase[0].text
    assert "🏷️ UVP 59,99 € (-17 %)" in chase[0].text
    assert chase[0].link == TCG_TTB


def test_tcgcheck_erster_blick_ohne_uvp_flut(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("TCGCHECK Dunkelnacht", TCG_DE)], filter_=KategorieFilter(nur_mit=["Top Trainer"]))
    lauf(e, speicher, {TCG_DE: lies("tcgcheck/set_dunkelnacht_de.html")}, melder)   # TTB schon zur UVP
    assert not any(k.art == "chase" for n in melder.nachrichten for k in n["kaesten"])
    uebersicht = melder.nachrichten[0]["kaesten"][0].text
    assert "💎 zur UVP" in uebersicht
    lauf(e, speicher, {TCG_DE: lies("tcgcheck/set_dunkelnacht_de.html")}, melder, minuten=20)
    assert not any(k.art == "chase" for n in melder.nachrichten for k in n["kaesten"])   # auch später nicht


def test_eigener_chasepreis_hat_vorrang_vor_der_uvp(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("TCGCHECK Dunkelnacht", TCG_DE)], suche=[("Dunkelnacht", ["Dunkelnacht"])],
                      filter_=KategorieFilter(nur_mit=["Top Trainer"]))
    e.watchlist[0].chase = {"Top-Trainer-Box DE": 45}
    leer = "<html></html>"
    such = {"https://www.gate-to-the-games.de/?suche=Dunkelnacht&af=100": leer,
            "https://www.card-corner.de/?suche=Dunkelnacht&af=50": leer}
    lauf(e, speicher, {TCG_DE: _mit_ttb_preis("64.99"), **such}, melder)
    lauf(e, speicher, {TCG_DE: _mit_ttb_preis("49.99"), **such}, melder, minuten=20)
    # 49,99 € liegt unter der UVP, aber nicht unter deinen 45 € → kein 🚨
    assert not any(k.art == "chase" for n in melder.nachrichten for k in n["kaesten"])


def test_viele_neue_listen_ergeben_eine_uebersicht(speicher):
    melder = FalscherMelder()
    tcg = [(f"TCGCHECK {i}", f"https://www.tcgcheck.de/pokemon/set/de/set{i}/index") for i in range(7)]
    e = einstellungen(kategorien=tcg, filter_=KategorieFilter(nur_mit=["Display", "Top Trainer"], ohne=["Case"]))
    seiten = {link: lies("tcgcheck/set_dunkelnacht_de.html") for _, link in tcg}
    lauf(e, speicher, seiten, melder)
    titel = [k.titel for n in melder.nachrichten for k in n["kaesten"]]
    assert titel == ["📋 7 Listen neu überwacht"]
    text = melder.nachrichten[0]["kaesten"][0].text
    assert "TCGCHECK 0" in text and "💎" in text
    lauf(e, speicher, seiten, melder, minuten=20)            # danach: gemerkt, nichts Neues
    assert len(melder.nachrichten) == 1
