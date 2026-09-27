"""Tests für Deal-Feeds (mydealz-RSS)."""

from pathlib import Path

import pytest

from bot.feeds import FeedFehler, lies_rss
from bot.einstellungen import KategorieFilter
from tests.test_lauf import FalscherMelder, einstellungen, lauf, speicher  # noqa: F401 (Fixture)

FEED = (Path(__file__).parent / "beispiele" / "mydealz" / "beispiel_feed.xml").read_text(encoding="utf-8")
FEED_URL = "https://www.mydealz.de/rss/gruppe/pokemon"
FILTER = KategorieFilter(nur_mit=["Display", "Top-Trainer", "Collection", "Kollektion"], ohne=["LEGO"])


def mit_feed(**kwargs):
    e = einstellungen(filter_=FILTER, **kwargs)
    from bot.einstellungen import Kategorie
    e.feeds = [Kategorie("mydealz Pokémon", FEED_URL)]
    return e


def test_feed_lesen():
    deals = lies_rss(FEED)
    assert len(deals) == 4
    netto = deals[0]
    assert netto.haendler == "Netto Marken-Discount"
    assert netto.preis == 37.99
    assert netto.titel.startswith("Pokémon First Partner Illustration Collection")
    assert not netto.mit_einladung          # „ohne Einladung“
    assert deals[1].mit_einladung            # „[Prime Einladung]“


def test_kaputter_feed():
    with pytest.raises(FeedFehler):
        lies_rss("<html>kein RSS</html")


def test_erster_blick_dann_nur_neue_deals(speicher):
    melder = FalscherMelder()
    e = mit_feed()
    lauf(e, speicher, {FEED_URL: FEED}, melder)
    assert melder.titel == ["📋 Neu überwacht: mydealz Pokémon"]
    assert "LEGO" not in melder.nachrichten[0]["kaesten"][0].text   # vom Filter aussortiert
    # Gleicher Feed nochmal → still
    lauf(e, speicher, {FEED_URL: FEED}, melder, minuten=15)
    assert len(melder.nachrichten) == 1
    # Ein neuer Deal kommt dazu → Ping
    neu = FEED.replace("</channel>", """<item>
      <pepper:merchant name="Kaufland" price="54,99€"/>
      <title><![CDATA[Pokémon Optimale Ordnung Top-Trainer-Box zur UVP]]></title>
      <link>https://www.mydealz.de/deals/optimale-ordnung-ttb-2844010</link>
      <guid>https://www.mydealz.de/deals/optimale-ordnung-ttb-2844010</guid></item></channel>""")
    lauf(e, speicher, {FEED_URL: neu}, melder, minuten=30)
    kasten = melder.nachrichten[-1]["kaesten"][0]
    assert kasten.titel == "📰 Pokémon Optimale Ordnung Top-Trainer-Box zur UVP"
    assert "**Kaufland** · 54,99 €" in kasten.text
    assert kasten.link == "https://www.mydealz.de/deals/optimale-ordnung-ttb-2844010"


def test_einladung_wird_markiert(speicher):
    melder = FalscherMelder()
    e = mit_feed()
    ohne_amazon = FEED.replace("<guid>https://www.mydealz.de/deals/pokemon-dunkelnacht-top-trainer-box-2844001</guid>",
                               "<guid>alt</guid>")
    lauf(e, speicher, {FEED_URL: ohne_amazon}, melder)           # Erster Blick ohne den Amazon-Deal …
    speicher._db.execute("DELETE FROM meta WHERE schluessel LIKE 'deal:%pokemon-dunkelnacht%'")
    speicher._db.commit()
    lauf(e, speicher, {FEED_URL: FEED}, melder, minuten=15)      # … jetzt taucht er „neu“ auf
    kasten = melder.nachrichten[-1]["kaesten"][0]
    assert "Nur auf Einladung" in kasten.text
    assert kasten.farbe == 0xF1C40F


def test_maximalpreis_des_sets_gilt_auch_fuer_deals(speicher):
    melder = FalscherMelder()
    e = mit_feed(suche=[("Fatale Flammen", ["Fatale Flammen"])])
    e.watchlist[0].regeln.max_preis = 180                        # Display für 203,90 € ist zu teuer
    ohne_display = FEED.replace("pokemon-fatale-flammen-display-2844003</guid>", "x</guid>")
    leer = "<html><body>Keine Treffer</body></html>"
    suche = {"https://www.gate-to-the-games.de/?suche=Fatale+Flammen&af=100": leer,
             "https://www.card-corner.de/?suche=Fatale+Flammen&af=50": leer}
    lauf(e, speicher, {FEED_URL: ohne_display, **suche}, melder)
    melder.nachrichten.clear()
    lauf(e, speicher, {FEED_URL: FEED, **suche}, melder, minuten=15)
    assert melder.nachrichten == []  # kein Ping für das Display für 203,90 € (Maximalpreis 180 €)
