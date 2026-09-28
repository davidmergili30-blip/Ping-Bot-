"""Deal-Feeds (RSS), z. B. die Pokémon-Gruppe von mydealz.

RSS-Feeds sind extra dafür gemacht, von Programmen gelesen zu werden. Über mydealz
erfährt der Bot auch von Drops bei Händlern, die er selbst nicht abfragen kann
(Netto, Amazon, Kaufland, MediaMarkt …) – sobald die Community den Deal postet.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from bot.adapter.basis import preis_als_zahl

PEPPER = "{http://www.pepper.com/rss}"  # Zusatzfelder von mydealz (Händler, Preis)


class FeedFehler(Exception):
    """Der Feed ließ sich nicht lesen (z. B. kaputtes XML)."""


@dataclass
class Deal:
    guid: str
    titel: str
    link: str
    haendler: str | None = None
    preis: float | None = None
    zeit: str | None = None

    @property
    def mit_einladung(self) -> bool:
        """Amazon & Co. verkaufen manche Produkte nur „auf Einladung“."""
        text = " ".join(self.titel.lower().split())
        if "einladung" not in text:
            return False
        return not any(w in text for w in ("ohne einladung", "keine einladung", "kein einladung"))


def lies_rss(xml_text: str) -> list[Deal]:
    try:
        wurzel = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as fehler:
        raise FeedFehler(f"Feed ist kein gültiges RSS ({fehler}).") from None
    deals = []
    for item in wurzel.iter("item"):
        titel = " ".join((item.findtext("title") or "").split())
        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not titel or not guid:
            continue
        haendler_el = item.find(f"{PEPPER}merchant")
        deals.append(Deal(
            guid=guid,
            titel=titel,
            link=link or guid,
            haendler=haendler_el.get("name") if haendler_el is not None else None,
            preis=preis_als_zahl(haendler_el.get("price")) if haendler_el is not None else None,
            zeit=(item.findtext("pubDate") or "").strip() or None,
        ))
    return deals
