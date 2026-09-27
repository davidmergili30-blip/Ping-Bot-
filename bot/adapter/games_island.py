"""Adapter für Games Island – über deren offizielle Datenquelle für Programme.

Games Island bietet unter https://crawlme.games-island.eu eine schlichte Liste an, die extra
für Programme gedacht ist: pro Produkt nur Name, Link und Status. Die Regeln dort:
- höchstens 5 Anfragen in 5 Minuten → der Bot wartet 65 Sekunden zwischen zwei Anfragen
- ehrlicher User-Agent mit Kontakt → steht in config.yaml
- Links für Menschen zeigen auf games-island.eu → so steht es auch im Discord-Ping
- keine Preise ausgeben → die Liste enthält keine; im Ping steht „Preis im Shop“
- Scalper sind nicht willkommen → der Bot ist nur ein privater Preisalarm
- wer sich nicht daran hält, landet auf banned.games-island.eu → erkennt bot/abruf.py als Sperre

So sieht eine Zeile aus:
    <tr class="artikel status_Vorverkauf"><td><a href="https://games-island.eu/…">Name</a></td>
    <td>Vorverkauf - 2026-11-04</td></tr>
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date

from bs4 import BeautifulSoup, Tag

from bot.adapter.basis import CheckErgebnis, ListenEintrag, ShopAdapter, domain_von, ohne_anker
from bot.status import Status

ABRUF_DOMAIN = "crawlme.games-island.eu"
ISO_DATUM = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# Status-Klasse in der Liste → unser Status (kleingeschrieben, die Seite ist da nicht einheitlich)
STATUS = {
    "status_auflager": Status.BESTELLBAR,
    "status_vorverkauf": Status.VORBESTELLBAR,
    "status_ankuendigung": Status.BALD,
    "status_ausverkauft": Status.AUSVERKAUFT,
}


class GamesIsland(ShopAdapter):
    name = "Games Island"
    domains = ("games-island.eu",)
    min_abstand_sekunden = 65  # 5 Anfragen pro 5 Minuten erlaubt → sicherheitshalber etwas mehr Pause

    def abruf_domains(self) -> tuple[str, ...]:
        return (ABRUF_DOMAIN,)

    def passt_zu(self, url: str) -> bool:
        return domain_von(url) in (*self.domains, ABRUF_DOMAIN)

    def abruf_url(self, url: str) -> str:
        """https://games-island.eu/c/Pokemon/… → https://crawlme.games-island.eu/c/Pokemon/…"""
        teile = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit(("https", ABRUF_DOMAIN, teile.path or "/", teile.query, ""))

    # --- Kategorie (mehrere Produkte) -----------------------------------------------

    def erkenne_liste(self, html: str, url: str, heute: date | None = None) -> list[ListenEintrag]:
        eintraege: dict[str, ListenEintrag] = {}
        for zeile in BeautifulSoup(html, "html.parser").select("tr.artikel"):
            eintrag = _lies_zeile(zeile)
            if eintrag is not None:
                # Dasselbe Produkt kann in zwei Unterkategorien stehen – nur einmal zählen
                eintraege.setdefault(eintrag.url, eintrag)
        return list(eintraege.values())

    # --- Einzelnes Produkt ---------------------------------------------------------

    def erkenne_produkt(self, html: str, url: str, heute: date | None = None) -> CheckErgebnis:
        soup = BeautifulSoup(html, "html.parser")
        gesucht = _pfad(url)
        for zeile in soup.select("tr.artikel"):
            eintrag = _lies_zeile(zeile)
            if eintrag is not None and _pfad(eintrag.url) == gesucht:
                return eintrag.ergebnis
        if soup.select_one("tr.status_NotFound, tr.status_notfound"):
            # Die Seite sagt „Nicht auf Lager oder nicht gefunden“. Als AUSVERKAUFT merken:
            # Taucht das Produkt wieder auf, gibt es so einen Ping (AUSVERKAUFT → BESTELLBAR).
            return CheckErgebnis(Status.AUSVERKAUFT, ohne_preis=True,
                                 hinweis="Games Island: nicht auf Lager (oder der Link stimmt nicht)")
        return CheckErgebnis(Status.UNBEKANNT, hinweis="Produkt nicht in der Games-Island-Liste gefunden")


def _lies_zeile(zeile: Tag) -> ListenEintrag | None:
    link_el = zeile.select_one("a[href]")
    if link_el is None:
        return None
    link = ohne_anker(link_el["href"])
    if domain_von(link) != "games-island.eu":
        return None
    titel = " ".join(link_el.get_text(" ").split()) or None
    zellen = zeile.find_all("td")
    status_text = " ".join(zellen[-1].get_text(" ").split()) if len(zellen) > 1 else ""

    status = Status.UNBEKANNT
    for klasse in zeile.get("class", []):
        status = STATUS.get(klasse.lower(), status)
    liefertermin = None
    if status in (Status.VORBESTELLBAR, Status.BALD):
        treffer = ISO_DATUM.search(status_text)
        if treffer:
            jahr, monat, tag = treffer.groups()
            liefertermin = f"{tag}.{monat}.{jahr}"  # 2026-11-04 → 04.11.2026
    hinweis = None if status != Status.UNBEKANNT else f"Unbekannter Status bei Games Island: „{status_text}“"
    return ListenEintrag(url=link, ergebnis=CheckErgebnis(
        status=status, titel=titel, verkaeufer="Shop", liefertermin=liefertermin, hinweis=hinweis,
        ohne_preis=True))


def _pfad(url: str) -> str:
    return urllib.parse.urlsplit(url).path.rstrip("/").lower()
