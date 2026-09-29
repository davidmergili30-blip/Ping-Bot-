"""Adapter für Shops mit Shopify (z. B. cardcosmos, Card-Knights, Play-Maniac).

Jeder Shopify-Shop bietet zu jeder Abteilung („Collection“) eine maschinenlesbare Liste an:
    https://shop.de/collections/pokemon-booster-displays/products.json?limit=250
Darin steht pro Produkt u. a. der Name, die Schlagwörter (tags) und je Variante Preis und
„available“ (true = bestellbar). Das ist viel stabiler, als das Aussehen der Seite auszulesen.

Vorbestellungen: Shopify kennt dafür kein eigenes Feld. Liegt die Abteilung unter einem Namen wie
„vorbestellen“, „vorverkauf“, „release-kalender“ oder „bald-im-shop“, oder steht es im Produktnamen,
gilt ein verfügbares Produkt als VORBESTELLBAR.

Achtung: Manche Shops lassen „ausverkauft“ nie zu (Verkauf ohne Lager). Dort ist JEDES Produkt
„available“ – solche Shops werden nicht eingetragen (z. B. TCGViert, geprüft am 29.09.2026).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date

from bot.adapter.basis import CheckErgebnis, ListenEintrag, ShopAdapter, domain_von, preis_als_zahl
from bot.produkte import produktart
from bot.status import Status

PRO_SEITE = 250          # mehr erlaubt Shopify nicht
MAX_SEITEN = 4
VORBESTELLUNG = re.compile(r"vorbestell|vorverkauf|pre-?order|release|bald-im-shop|coming-soon", re.I)
# Schlagwörter, die eine Produktart verraten, wenn sie im Namen fehlt (z. B. „… Phantasmal Flames - EN“)
ART_TAGS = {"display": "Display", "elite trainer-box": "Top-Trainer-Box", "elite trainer box": "Top-Trainer-Box",
            "top trainer box": "Top-Trainer-Box", "bundle": "Booster Bundle", "bundles": "Booster Bundle",
            "kollektionen": "Kollektion", "collection": "Kollektion", "tin": "Mini-Tin"}


class ShopifyShop(ShopAdapter):
    def __init__(self, name: str, domains: tuple[str, ...]):
        self.name = name
        self.domains = domains

    def abruf_url(self, url: str) -> str:
        """Abteilung → ihre JSON-Liste, Produktseite → ihr JSON (mit „available“ je Variante)."""
        teile = urllib.parse.urlsplit(url)
        pfad = teile.path.rstrip("/")
        if pfad.endswith(".json") or pfad.endswith(".js"):
            return url
        abfrage = dict(urllib.parse.parse_qsl(teile.query))
        if "/products/" in pfad:
            return urllib.parse.urlunsplit((teile.scheme, teile.netloc, pfad + ".js", "", ""))
        neu = {"limit": str(PRO_SEITE)}
        if abfrage.get("page"):
            neu["page"] = abfrage["page"]
        return urllib.parse.urlunsplit((teile.scheme, teile.netloc, pfad + "/products.json",
                                        urllib.parse.urlencode(neu), ""))

    def naechste_seite(self, url: str, anzahl: int) -> str | None:
        teile = urllib.parse.urlsplit(url)
        seite = int(dict(urllib.parse.parse_qsl(teile.query)).get("page", "1"))
        if anzahl < PRO_SEITE or seite >= MAX_SEITEN:
            return None
        return urllib.parse.urlunsplit((teile.scheme, teile.netloc, teile.path, f"page={seite + 1}", ""))

    def erkenne_liste(self, text: str, url: str, heute: date | None = None) -> list[ListenEintrag]:
        try:
            produkte = json.loads(text).get("products", [])
        except (ValueError, AttributeError):
            return []
        vorbestell_abteilung = VORBESTELLUNG.search(urllib.parse.urlsplit(url).path) is not None
        basis = f"https://{urllib.parse.urlsplit(url).netloc}"
        eintraege = []
        for p in produkte:
            if not isinstance(p, dict) or not p.get("handle"):
                continue
            ergebnis = _ergebnis(p, vorbestell_abteilung)
            eintraege.append(ListenEintrag(url=f"{basis}/products/{p['handle']}", ergebnis=ergebnis))
        return eintraege

    def erkenne_produkt(self, text: str, url: str, heute: date | None = None) -> CheckErgebnis:
        try:
            p = json.loads(text)
        except ValueError:
            return CheckErgebnis(Status.UNBEKANNT, hinweis="Keine Produktdaten (Shopify) gefunden")
        if not isinstance(p, dict) or "variants" not in p:
            return CheckErgebnis(Status.UNBEKANNT, hinweis="Keine Produktdaten (Shopify) gefunden")
        # Das .js-Format nennt Preise in Cent
        for v in p["variants"]:
            if isinstance(v.get("price"), int):
                v["price"] = f"{v['price'] / 100:.2f}"
        return _ergebnis(p, vorbestell_abteilung=False)

    def passt_zu(self, url: str) -> bool:
        return domain_von(url) in self.domains


def _ergebnis(p: dict, vorbestell_abteilung: bool) -> CheckErgebnis:
    varianten = [v for v in p.get("variants", []) if isinstance(v, dict)]
    verfuegbar = [v for v in varianten if v.get("available")]
    preise = [preis_als_zahl(str(v.get("price"))) for v in (verfuegbar or varianten)]
    preise = [x for x in preise if x is not None]
    titel = " ".join(str(p.get("title", "")).split())
    tags = p.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    # Fehlt die Produktart im Namen, aus den Schlagwörtern ergänzen („… - EN“ → „… - EN (Display)“)
    if produktart(titel) is None:
        art = next((ART_TAGS[t.lower()] for t in tags if t.lower() in ART_TAGS), None)
        if art:
            titel = f"{titel} ({art})"
    if not verfuegbar:
        status = Status.AUSVERKAUFT
    elif vorbestell_abteilung or VORBESTELLUNG.search(titel) or any(VORBESTELLUNG.search(t) for t in tags):
        status = Status.VORBESTELLBAR
    else:
        status = Status.BESTELLBAR
    return CheckErgebnis(status=status, preis=min(preise) if preise else None, titel=titel or None,
                         verkaeufer="Shop")
