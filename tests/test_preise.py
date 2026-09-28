"""Tests im kompletten Lauf: Maximalpreis je Produktart und Preisvergleich zwischen Shops."""

from pathlib import Path

from bot.einstellungen import KategorieFilter
from bot.status import Status
from tests.test_lauf import FATALE, SET_FILTER, FalscherMelder, einstellungen, lauf, suchseiten

GI_BEISPIEL = Path(__file__).parent / "beispiele" / "games_island" / "liste_booster_displays.html"
GI_KATEGORIE = "https://games-island.eu/c/Pokemon/Booster-Displays"
GI_ABRUF = "https://crawlme.games-island.eu/c/Pokemon/Booster-Displays"
GI_FATALE = "https://games-island.eu/Pokemon-TCG-Mega-Entwicklung-02-Fatale-Flammen-Booster-Display-Deutsch"
GTTG_DISPLAY = "https://www.gate-to-the-games.de/Pokemon-Karten-Mega-Entwicklung-Fatale-Flammen-Display-36-Booster-deutsch"
GTTG_TTB = "https://www.gate-to-the-games.de/Pokemon-Karten-Mega-Entwicklung-Fatale-Flammen-Top-Trainer-Box-deutsch"


def gi_liste(fatale_verfuegbar: bool) -> str:
    text = GI_BEISPIEL.read_text(encoding="utf-8")
    if fatale_verfuegbar:
        text = text.replace(f'status_Ausverkauft"><td><a href="{GI_FATALE}"', f'status_aufLager"><td><a href="{GI_FATALE}"')
    return text


def mit_preisen(preise, **extra):
    e = einstellungen(suche=FATALE, filter_=SET_FILTER, **extra)
    e.watchlist[0].preise = preise
    return e


def restock(speicher, url, preis=1.0):
    """So tun, als wäre das Produkt beim letzten Mal ausverkauft gewesen."""
    speicher.setze_stand(url, "Gate to the Games", "x", Status.AUSVERKAUFT, preis)


def test_preis_der_produktart_blockiert_zu_teures_display(speicher):
    melder = FalscherMelder()
    e = mit_preisen({"Display": 300, "Top-Trainer-Box": 200})     # Display kostet 399,90 €, TTB 149,90 €
    lauf(e, speicher, suchseiten(), melder)
    restock(speicher, GTTG_DISPLAY)
    restock(speicher, GTTG_TTB)
    lauf(e, speicher, suchseiten(), melder, minuten=20)
    titel = [k.titel for k in melder.nachrichten[-1]["kaesten"]]
    assert not any("Display" in t for t in titel)                  # 399,90 € > 300 € → kein Ping
    ttb = next(k for k in melder.nachrichten[-1]["kaesten"] if "Top Trainer Box" in k.titel)
    assert "💶 Dein Maximalpreis: 200,00 €" in ttb.text


def test_ohne_preis_der_art_gilt_der_preis_des_sets(speicher):
    melder = FalscherMelder()
    e = mit_preisen({"Top-Trainer-Box": 100})                      # TTB 149,90 € > 100 €
    e.watchlist[0].regeln.max_preis = 450                           # ganzes Set
    lauf(e, speicher, suchseiten(), melder)
    restock(speicher, GTTG_DISPLAY)
    restock(speicher, GTTG_TTB)
    lauf(e, speicher, suchseiten(), melder, minuten=20)
    titel = [k.titel for k in melder.nachrichten[-1]["kaesten"]]
    assert any("Display" in t for t in titel)                      # 399,90 € ≤ 450 € (Set-Preis)
    assert not any("Top Trainer Box" in t for t in titel)          # Preis der Art gewinnt


def test_preis_gilt_auch_in_kategorien_und_ohne_shop_preis_kommt_ein_hinweis(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GI", GI_KATEGORIE)], suche=FATALE,
                      filter_=KategorieFilter(nur_mit=["Display"]))
    e.watchlist[0].preise = {"Display": 180}
    e.vertrauenswuerdige_shops.append("games-island.eu")
    leer = {url: "<html></html>" for url in suchseiten()}
    lauf(e, speicher, {**leer, GI_ABRUF: gi_liste(False)}, melder)
    lauf(e, speicher, {**leer, GI_ABRUF: gi_liste(True)}, melder, minuten=20)
    kasten = melder.nachrichten[-1]["kaesten"][0]
    assert kasten.titel.startswith("🟢 BESTELLBAR – Pokemon TCG - Mega-Entwicklung 02: Fatale Flammen Booster Display")
    # Games Island nennt keinen Preis → der Bot kann die Grenze nicht prüfen und sagt das dazu
    assert "💶 Dein Maximalpreis: 180,00 € – bitte den Preis im Shop prüfen" in kasten.text


def test_preisvergleich_zeigt_andere_shops(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GI", GI_KATEGORIE)], suche=FATALE, filter_=SET_FILTER)
    seiten = {**suchseiten(), GI_ABRUF: gi_liste(True)}
    lauf(e, speicher, seiten, melder)
    restock(speicher, GTTG_DISPLAY)
    lauf(e, speicher, seiten, melder, minuten=20)
    kasten = next(k for k in melder.nachrichten[-1]["kaesten"] if k.titel.startswith("🟢 BESTELLBAR – Mega-Entw"))
    assert f"🔎 Auch verfügbar: [Games Island]({GI_FATALE}) Preis im Shop" in kasten.text


def test_preisvergleich_nicht_bei_anderer_sprache_oder_ausverkauft(speicher):
    melder = FalscherMelder()
    e = einstellungen(kategorien=[("GI", GI_KATEGORIE)], suche=FATALE, filter_=SET_FILTER)
    seiten = {**suchseiten(), GI_ABRUF: gi_liste(False)}           # bei Games Island ausverkauft
    lauf(e, speicher, seiten, melder)
    restock(speicher, GTTG_DISPLAY)
    lauf(e, speicher, seiten, melder, minuten=20)
    kasten = next(k for k in melder.nachrichten[-1]["kaesten"] if k.titel.startswith("🟢 BESTELLBAR – Mega-Entw"))
    assert "Auch verfügbar" not in kasten.text
