"""Tests: Art, Set und Sprache aus echten Produktnamen der Shops (Stand 28.09.2026)."""

import pytest

from bot.einstellungen import Produkt, Regeln
from bot.produkte import (
    art_aus_eingabe,
    produktart,
    regeln_fuer,
    set_fuer,
    set_name_aus_titel,
    sprache,
    vergleichs_schluessel,
)

WATCHLIST = [
    Produkt("30 Jahre", [], Regeln(), suche=["30 Jahre", "30th Celebration"]),
    Produkt("Dunkelnacht", [], Regeln(), suche=["Dunkelnacht", "Pitch Black", "Abyss Eye"],
            preise={"Display": 180, "Top-Trainer-Box": 60}),
    Produkt("Erhabene Helden", [], Regeln(max_preis=150), suche=["Erhabene Helden", "Ascended Heroes"],
            preise={"Mini-Tin": 15}),
    Produkt("Wachsendes Chaos", [], Regeln(), suche=["Wachsendes Chaos", "Chaos Rising", "Ninja Spinner"]),
]


@pytest.mark.parametrize("titel, art", [
    ("Mega-Entwicklung Fatale Flammen Display (36 Booster) (deutsch)", "Display"),
    ("Pokemon Fatale Flammen 18er Display", "Display"),
    ("Pokemon Dunkelnacht Top Trainer Box", "Top-Trainer-Box"),
    ("Mega-Entwicklung Erhabene Helden Top Trainer Box (deutsch)", "Top-Trainer-Box"),
    ("Pokemon Pitch Black Elite Trainer Box", "Top-Trainer-Box"),
    ("Pokemon TCG - Mega Evolution - Elite Trainer Box - Englisch - Set (beide Elite Trainer Boxen)", "Top-Trainer-Box"),
    ("Pokemon 30 Jahre – Top-Trainer-Box (deutsch) *LIMITIERT 1 pro Person", "Top-Trainer-Box"),
    ("Mega-Entwicklung Dunkelnacht Booster Bundle (deutsch)", "Booster Bundle"),
    ("Pokemon Erhabene Helden Booster Bundle Display", "Display"),
    ("Mega-Entwicklung Erhabene Helden Mini Tin Riolu & Flampion (deutsch)", "Mini-Tin"),
    ("Pokemon Ascended Heroes - Mini Tins", "Mini-Tin"),
    ("Pokemon TCG - Crown Zenith Mini-Tin - Englisch -", "Mini-Tin"),
    ("Mega-Entwicklung Erhabene Helden Mini Tin Display sealed (deutsch)", "Mini-Tin-Display"),
    ("Pokemon TCG - Crown Zenith Mini-Tin - Englisch - Display (jede Tin 2x)", "Mini-Tin-Display"),
    ("Pokemon 30 Jahre Ultra-Premium-Kollektion Nacht (deutsch) VORVERKAUF", "Kollektion"),
    ("Pokemon Ascended Heroes - Tech Sticker Collection - Charmander", "Kollektion"),
    ("Mega-Entwicklung Fatale Flammen Booster (deutsch)", None),
])
def test_produktart(titel, art):
    assert produktart(titel) == art


@pytest.mark.parametrize("eingabe, art", [
    ("Display", "Display"), ("ttb", "Top-Trainer-Box"), ("Top-Trainer-Box", "Top-Trainer-Box"),
    ("ETB", "Top-Trainer-Box"), ("booster bundle", "Booster Bundle"), ("Mini-Tin", "Mini-Tin"),
    ("mini tins", "Mini-Tin"), ("Mini-Tin-Display", "Mini-Tin-Display"), ("Kollektionen", "Kollektion"),
    ("Collection", "Kollektion"), ("Booster", None), ("", None),
])
def test_art_aus_eingabe(eingabe, art):
    assert art_aus_eingabe(eingabe) == art


@pytest.mark.parametrize("titel, erwartet", [
    ("Mega-Entwicklung Dunkelnacht Display (36 Booster) (deutsch)", "DE"),
    ("Pokemon Dunkelnacht Display", "DE"),                          # Card-Corner: ohne Angabe, deutscher Name
    ("Mega Evolution Pitch Black Display (36 Booster) (englisch)", "EN"),
    ("Pokemon Pitch Black Display", "EN"),                          # Card-Corner: ohne Angabe, englischer Name
    ("Pokemon Abyss Eye (M5) Display", "JP"),                       # Card-Corner: japanisch nur am Kürzel
    ("Pokemon Abyss Eye Display (Koreanisch)", "KR"),
    ("Pokemon Pitch Black Display - Chinesisch", "CN"),
    ("Pokemon TCG - Mega Evolution 05: Pitch Black Booster Display (18 Boosters) - Englisch", "EN"),
])
def test_sprache(titel, erwartet):
    produkt, begriff = set_fuer(titel, WATCHLIST)
    assert sprache(titel, begriff, produkt.name) == erwartet


def test_gleiches_produkt_in_verschiedenen_shops_hat_gleichen_schluessel():
    gttg = vergleichs_schluessel("Mega-Entwicklung Dunkelnacht Display (36 Booster) (deutsch)", WATCHLIST)
    cc = vergleichs_schluessel("Pokemon Dunkelnacht Display", WATCHLIST)
    assert gttg == cc == ("Dunkelnacht", "Display", "DE")
    en_gttg = vergleichs_schluessel("Mega Evolution Pitch Black Display (36 Booster) (englisch)", WATCHLIST)
    en_cc = vergleichs_schluessel("Pokemon Pitch Black Display", WATCHLIST)
    assert en_gttg == en_cc == ("Dunkelnacht", "Display", "EN")
    assert vergleichs_schluessel("Pokemon Abyss Eye (M5) Display", WATCHLIST) == ("Dunkelnacht", "Display", "JP")


@pytest.mark.parametrize("titel", [
    "Pokemon Fatale Flammen 18er Display",                              # kein Set der Test-Watchlist
    "Pokemon Dunkelnacht 18er Display",                                 # halbes Display
    "Pokemon Pitch Black Pokemon Center ETB",                           # Sonderedition
    "Pokemon TCG - Scarlet & Violet 10: Destined Rivals Elite Trainer Box - Englisch - Sealed Case",
    "Mega-Entwicklung Erhabene Helden Mini Tin Riolu & Flampion (deutsch)",   # viele Varianten
    "Pokemon 30 Jahre Poster Kollektion",                               # viele Varianten
])
def test_nicht_vergleichbar(titel):
    assert vergleichs_schluessel(titel, WATCHLIST) is None


def test_maximalpreis_je_produktart():
    standard = Regeln(max_preis=999)
    # Preis der Produktart im Set
    assert regeln_fuer("Pokemon Dunkelnacht Display", WATCHLIST, standard).max_preis == 180
    assert regeln_fuer("Pokemon Pitch Black Elite Trainer Box", WATCHLIST, standard).max_preis == 60
    # Art ohne eigenen Preis → Preis des ganzen Sets (hier keiner)
    assert regeln_fuer("Pokemon Dunkelnacht Booster Bundle", WATCHLIST, standard).max_preis is None
    # Set mit Preis fürs ganze Set + eigener Preis für Mini-Tins
    assert regeln_fuer("Pokemon Erhabene Helden Mini Tin", WATCHLIST, standard).max_preis == 15
    assert regeln_fuer("Pokemon Erhabene Helden Display", WATCHLIST, standard).max_preis == 150
    # Kein Set der Watchlist → Standard-Regeln
    assert regeln_fuer("Pokemon Delta Herrschaft Display", WATCHLIST, standard).max_preis == 999
    # Set ist schon bekannt (Set-Suche)
    assert regeln_fuer("Irgendein Display", WATCHLIST, standard, produkt=WATCHLIST[1]).max_preis == 180


@pytest.mark.parametrize("titel, name", [
    ("Mega-Entwicklung Delta Herrschaft Display (36 Booster) (deutsch) VORVERKAUF", "Delta Herrschaft"),
    ("Mega-Entwicklung Delta Herrschaft Top Trainer Box (deutsch) VORVERKAUF", "Delta Herrschaft"),
    ("Pokemon TCG - Mega-Entwicklung 02.5: Erhabene Helden Booster Bundle - Deutsch", "Erhabene Helden"),
    ("Pokemon Abyss Eye (M5) Display", "Abyss Eye"),
    ("Phantasmal Flames Expansion Elite Trainer Box (englisch)", "Phantasmal Flames"),
    ("Pokemon TCG - Karmesin & Purpur 10: Ewige Rivalen Booster Display - Deutsch", "Ewige Rivalen"),
    ("Mega Evolution Perfect Order Booster Bundle (englisch)", "Perfect Order"),
    ("Pokemon TCG - Mega Evolution: Mini Tin Display (10 Tins) - Englisch", None),   # kein Set-Name
    ("Ultra Pro - Pokémon Pokéball 2\" Sammelalbum", None),
    ("Pokemon 30 Jahre Top Trainer Box (deutsch) VORVERKAUF", "30 Jahre"),
    ("Pokemon TCG - Karmesin & Purpur 10.5: Schwarze Blitze Booster Bundle - Deutsch", "Schwarze Blitze"),
    ("MTG - Phyrexia: All Will Be One Set Booster Display - Englisch", None),       # anderes Spiel
    ("One Piece Card Game OP-13 Booster Display (englisch)", None),
    ("Pokemon TCG - Pokeball Tins Herbst 2026 Display (6 Tins) - Deutsch", None),      # kein Set
])
def test_set_name_aus_titel(titel, name):
    assert set_name_aus_titel(titel) == name
