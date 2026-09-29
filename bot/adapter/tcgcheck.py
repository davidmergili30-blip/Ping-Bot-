"""Adapter für TCGCHECK – einen Preisvergleich nur für Sammelkarten mit über 200 angebundenen Shops.

Die Set-Übersicht (z. B. https://www.tcgcheck.de/pokemon/set/de/dunkelnacht/index) zeigt für jedes
Produkt des Sets den GÜNSTIGSTEN Preis über alle Shops und die UVP – mit einer einzigen Abfrage.
Welcher Shop das ist, steht auf der Produktseite bei TCGCHECK (der Link im Ping führt dorthin).

So sieht eine Produktkarte aus (schema.org, gedacht für Suchmaschinen):
    <li itemtype="https://schema.org/Product">
      <a href="/pokemon/set/de/dunkelnacht/dunkelnacht-display" title="Dunkelnacht Display">
        … UVP 179,99 € … <h2 itemprop="name">Dunkelnacht Display</h2>
        <div itemprop="offers"> <meta itemprop="price" content="184.90">
                                <meta itemprop="availability" content="https://schema.org/InStock"> </div>
Ohne Angebote steht dort „Keine Angebote“ (und es gibt keinen Preis).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date

from bs4 import BeautifulSoup, Tag

from bot.adapter.basis import CheckErgebnis, ListenEintrag, ShopAdapter, preis_als_zahl, schema_status
from bot.status import Status

BASIS = "https://www.tcgcheck.de"
UVP_MUSTER = re.compile(r"UVP\s*([\d.,]+)\s*€")
SPRACHE_IM_PFAD = re.compile(r"/set/(de|en|jp)/")
INFO = "🔎 Günstigster Preis über alle Shops bei TCGCHECK – tipp auf die Überschrift, dort steht der Shop."


class TcgCheck(ShopAdapter):
    name = "TCGCHECK (Tiefstpreis)"
    domains = ("tcgcheck.de",)

    def erkenne_liste(self, html: str, url: str, heute: date | None = None) -> list[ListenEintrag]:
        sprache = _sprache(url)
        eintraege = []
        for karte in BeautifulSoup(html, "html.parser").select("#product-list > li"):
            eintrag = _lies_karte(karte, sprache)
            if eintrag is not None:
                eintraege.append(eintrag)
        return eintraege

    def erkenne_produkt(self, html: str, url: str, heute: date | None = None) -> CheckErgebnis:
        """Produktseite: günstigster Preis steht in den schema.org-Daten (AggregateOffer)."""
        soup = BeautifulSoup(html, "html.parser")
        for block in soup.select('script[type="application/ld+json"]'):
            try:
                daten = json.loads(block.get_text())
            except ValueError:
                continue
            if not isinstance(daten, dict) or daten.get("@type") != "Product":
                continue
            angebot = daten.get("offers") or {}
            preis = preis_als_zahl(str(angebot.get("lowPrice") or angebot.get("price") or ""))
            anzahl = angebot.get("offerCount")
            uvp = _uvp(soup.get_text(" "))
            titel = f"{daten.get('name')} ({_sprache(url)})" if daten.get("name") else None
            if preis is None or anzahl == 0:
                return CheckErgebnis(Status.AUSVERKAUFT, titel=titel, uvp=uvp, verkaeufer="verschiedene Shops")
            return CheckErgebnis(schema_status(angebot.get("availability")) or Status.BESTELLBAR, preis=preis,
                                 titel=titel, uvp=uvp, verkaeufer="verschiedene Shops", info=INFO)
        return CheckErgebnis(Status.UNBEKANNT, hinweis="Keine Produktdaten bei TCGCHECK gefunden")


def _lies_karte(karte: Tag, sprache: str) -> ListenEintrag | None:
    link_el = karte.select_one("a[href]")
    if link_el is None:
        return None
    name_el = karte.select_one("h2")
    name = " ".join((name_el.get_text(" ") if name_el else link_el.get("title", "")).split())
    if not name:
        return None
    # Sprache aus der Adresse anhängen – die Namen selbst sagen es nicht (wichtig für Preise je Sprache)
    titel = f"{name} ({sprache})"
    text = " ".join(karte.get_text(" ").split())
    uvp = _uvp(text)
    preis_el = karte.select_one('[itemprop="offers"] [itemprop="price"]')
    preis = preis_als_zahl(preis_el.get("content")) if preis_el else None
    if "Keine Angebote" in text or preis is None:
        status = Status.AUSVERKAUFT if "Keine Angebote" in text else Status.UNBEKANNT
        return ListenEintrag(url=urllib.parse.urljoin(BASIS, link_el["href"]),
                             ergebnis=CheckErgebnis(status, titel=titel, uvp=uvp, verkaeufer="verschiedene Shops"))
    verfuegbar = karte.select_one('[itemprop="offers"] [itemprop="availability"]')
    status = schema_status(verfuegbar.get("content") if verfuegbar else None) or Status.BESTELLBAR
    return ListenEintrag(url=urllib.parse.urljoin(BASIS, link_el["href"]), ergebnis=CheckErgebnis(
        status=status, preis=preis, titel=titel, uvp=uvp, verkaeufer="verschiedene Shops", info=INFO))


def _uvp(text: str) -> float | None:
    treffer = UVP_MUSTER.search(text or "")
    return preis_als_zahl(treffer.group(1)) if treffer else None


def _sprache(url: str) -> str:
    treffer = SPRACHE_IM_PFAD.search(url or "")
    return treffer.group(1).upper() if treffer else "DE"
