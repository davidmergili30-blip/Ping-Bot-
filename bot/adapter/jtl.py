"""Adapter für Shops mit JTL-Shop 5 (z. B. Gate to the Games und Card-Corner).

Woran der Status erkannt wird (in dieser Reihenfolge):
1. Banner „Ausverkauft“, rote Lieferampel (status-0) oder „Ausverkauft“ im Lieferstatus
   → immer AUSVERKAUFT. Wichtig, weil Shops ausverkaufte Vorbestellungen oft weiter mit
   „Verfügbar ab …“ und „PreOrder“ anzeigen (gesehen bei Gate to the Games und Card-Corner).
2. schema.org-Angabe des Hauptprodukts (maschinenlesbar, z. B. „PreOrder“)
3. „Verfügbar ab: 06.11.2026“ → Vorbestellung bzw. bald verfügbar
4. Lieferstatus-Ampel: status-2 (grün) / status-1 (knapp) = bestellbar, status-0 = ausverkauft
5. Banner „Auf Lager“ bzw. „Vorbestellen“ (manche Listen haben keine Lieferampel)
Passt nichts davon, heißt das Ergebnis UNBEKANNT – lieber ehrlich als falsch geraten.

Wichtig: Auf Produktseiten stehen auch Empfehlungen („Kunden kauften auch“) mit
eigenen Preisen. Die liegen in verschachtelten Produkt-Blöcken und werden übersprungen.
"""

from __future__ import annotations

import urllib.parse
from datetime import date

from bs4 import BeautifulSoup, Tag

from bot.adapter.basis import (
    CheckErgebnis,
    ListenEintrag,
    ShopAdapter,
    datum_aus_text,
    domain_von,
    ohne_anker,
    preis_als_zahl,
    schema_status,
)
from bot.status import Status

PRODUKT = '[itemtype*="schema.org/Product"]'
BANNER = "[class*=ribbon]"
AUSVERKAUFT_BANNER = "ribbon-7"  # Standard-Banner „Ausverkauft“ im JTL-Shop
# Texte im Lieferstatus, die sicher „nicht bestellbar“ bedeuten
AUSVERKAUFT_TEXTE = ("ausverkauft", "nicht verfügbar", "nicht lieferbar", "vergriffen")


class JtlShop(ShopAdapter):
    def __init__(self, name: str, domains: tuple[str, ...], treffer_pro_seite: int = 50):
        self.name = name
        self.domains = domains
        self.treffer_pro_seite = treffer_pro_seite

    def such_url(self, begriff: str, seite: int = 1) -> str | None:
        """z. B. https://www.card-corner.de/?suche=Dunkelnacht&af=50 (af = Treffer pro Seite)"""
        url = f"https://www.{self.domains[0]}/?suche={urllib.parse.quote_plus(begriff)}&af={self.treffer_pro_seite}"
        return url + (f"&seite={seite}" if seite > 1 else "")

    # --- Produktseite ------------------------------------------------------------

    def erkenne_produkt(self, html: str, url: str, heute: date | None = None) -> CheckErgebnis:
        heute = heute or date.today()
        soup = BeautifulSoup(html, "html.parser")
        haupt = soup.select_one(f"#result-wrapper{PRODUKT}") or soup.select_one(PRODUKT)
        if haupt is None:
            return CheckErgebnis(Status.UNBEKANNT, hinweis="Keine Produktdaten auf der Seite gefunden")

        titel_el = haupt.find("h1") or _eigenes(haupt, "[itemprop=name]")
        verfuegbarkeit = _eigenes(haupt, "[itemprop=availability]")
        preis_el = _eigenes(haupt, "[itemprop=price]")
        lieferstatus = _eigenes(haupt, ".delivery-status")
        termin_el = _eigenes(haupt, ".coming_soon") or _eigenes(haupt, ".availablefrom")
        anzahl = _eigenes(haupt, "input[name=anzahl]")
        banner = _alle_eigenen(haupt, BANNER)

        termin = datum_aus_text(termin_el.get_text(" ") if termin_el else None)
        status = _status(
            schema=schema_status(_wert(verfuegbarkeit)),
            klassen=_klassen(lieferstatus),
            termin=termin,
            heute=heute,
            ausverkauft_markiert=_ausverkauft_markiert(banner, lieferstatus),
            banner_text=_banner_text(banner),
        )
        return CheckErgebnis(
            status=status,
            preis=preis_als_zahl(_wert(preis_el)),
            titel=_text(titel_el),
            verkaeufer="Shop",
            mengenlimit=_mengenlimit(anzahl),
            liefertermin=f"{termin:%d.%m.%Y}" if termin and status in (Status.VORBESTELLBAR, Status.BALD) else None,
            hinweis=None if status != Status.UNBEKANNT else "Status auf der Seite nicht eindeutig",
        )

    # --- Kategorieseite -----------------------------------------------------------

    def erkenne_liste(self, html: str, url: str, heute: date | None = None) -> list[ListenEintrag]:
        heute = heute or date.today()
        soup = BeautifulSoup(html, "html.parser")
        eintraege: dict[str, ListenEintrag] = {}
        for box in soup.select(PRODUKT):
            link = _produktlink(box, self.domains)
            if not link or link in eintraege:
                continue
            lieferstatus = box.select_one(".delivery-status")
            termin = datum_aus_text(lieferstatus.get_text(" ") if lieferstatus else None)
            banner = box.select(BANNER)
            status = _status(
                schema=schema_status(_wert(box.select_one("[itemprop=availability]"))),
                klassen=_klassen(lieferstatus),
                termin=termin,
                heute=heute,
                ausverkauft_markiert=_ausverkauft_markiert(banner, lieferstatus),
                banner_text=_banner_text(banner),
            )
            name_el = box.select_one("[itemprop=name]")
            eintraege[link] = ListenEintrag(
                url=link,
                ergebnis=CheckErgebnis(
                    status=status,
                    preis=preis_als_zahl(_wert(box.select_one("[itemprop=price]"))),
                    titel=(name_el.get("content") or _text(name_el)) if name_el else None,
                    verkaeufer="Shop",
                    liefertermin=f"{termin:%d.%m.%Y}" if termin and status == Status.VORBESTELLBAR else None,
                ),
            )
        return list(eintraege.values())


# --- Hilfsfunktionen -------------------------------------------------------------

def _status(schema: Status | None, klassen: set[str], termin: date | None, heute: date,
            ausverkauft_markiert: bool = False, banner_text: str | None = None) -> Status:
    """Entscheidet den Status aus allen Hinweisen der Seite."""
    if ausverkauft_markiert:
        return Status.AUSVERKAUFT
    in_zukunft = termin is not None and termin > heute
    if schema == Status.VORBESTELLBAR:
        return Status.VORBESTELLBAR
    if schema == Status.BESTELLBAR:
        # Manche Shops markieren Vorbestellungen als „auf Lager“ – das Datum verrät es.
        return Status.VORBESTELLBAR if in_zukunft else Status.BESTELLBAR
    if schema == Status.AUSVERKAUFT:
        # Angekündigt, aber noch nicht bestellbar
        return Status.BALD if in_zukunft else Status.AUSVERKAUFT
    if schema is not None:
        return schema
    # Keine schema.org-Angabe → Lieferstatus-Ampel
    if "availablefrom" in klassen or "coming_soon" in klassen:
        return Status.VORBESTELLBAR if in_zukunft or termin is None else Status.BESTELLBAR
    if "status-2" in klassen or "status-1" in klassen:
        return Status.BESTELLBAR
    if "status-0" in klassen:
        return Status.AUSVERKAUFT
    # Letzter Hinweis: Banner am Produkt (z. B. bei Artikeln mit Varianten ohne Lieferampel)
    banner = (banner_text or "").lower()
    if "vorbestell" in banner:
        return Status.VORBESTELLBAR
    if "auf lager" in banner:
        return Status.BESTELLBAR
    return Status.UNBEKANNT


def _ausverkauft_markiert(banner: list[Tag], lieferstatus: Tag | None) -> bool:
    """True, wenn der Shop das Produkt irgendwo sichtbar als ausverkauft kennzeichnet.

    Es zählen ALLE Banner am Produkt (z. B. „Neu“ UND „Ausverkauft“) – im Zweifel lieber
    ausverkauft als ein falscher Ping.
    """
    for b in banner:
        if AUSVERKAUFT_BANNER in _klassen(b) or "ausverkauft" in b.get_text(" ").lower():
            return True
    if lieferstatus is not None:
        text = " ".join(lieferstatus.get_text(" ").split()).lower()
        if "status-0" in _klassen(lieferstatus) or any(w in text for w in AUSVERKAUFT_TEXTE):
            return True
    return False


def _eigenes(haupt: Tag, auswahl: str) -> Tag | None:
    """Erstes passendes Element, das NICHT zu einem verschachtelten Produkt (Empfehlung) gehört."""
    eigene = _alle_eigenen(haupt, auswahl)
    return eigene[0] if eigene else None


def _alle_eigenen(haupt: Tag, auswahl: str) -> list[Tag]:
    """Alle passenden Elemente, die NICHT zu einem verschachtelten Produkt (Empfehlung) gehören."""
    return [el for el in haupt.select(auswahl)
            if el.find_parent(attrs={"itemtype": lambda t: t and "schema.org/Product" in t}) is haupt]


def _banner_text(banner: list[Tag]) -> str | None:
    return " ".join(filter(None, (_text(b) for b in banner))) or None


def _wert(el: Tag | None) -> str | None:
    if el is None:
        return None
    return el.get("content") or el.get("href") or el.get_text(" ", strip=True) or None


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    return " ".join(el.get_text(" ").split()) or None


def _klassen(el: Tag | None) -> set[str]:
    if el is None:
        return set()
    return {k for kind in [el, *el.find_all(True)] for k in kind.get("class", [])}


def _mengenlimit(anzahl: Tag | None) -> int | None:
    try:
        return int(anzahl["max"]) if anzahl and anzahl.get("max") else None
    except ValueError:
        return None


def _produktlink(box: Tag, domains: tuple[str, ...]) -> str | None:
    for a in box.select("a[href]"):
        link = ohne_anker(a["href"])
        if domain_von(link) in domains and link.rstrip("/") != f"https://www.{domains[0]}":
            return link
    return None
