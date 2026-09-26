"""Adapter für Shops mit JTL-Shop 5 (z. B. Gate to the Games und Card-Corner).

Woran der Status erkannt wird (in dieser Reihenfolge):
1. schema.org-Angabe des Hauptprodukts (maschinenlesbar, z. B. „PreOrder“)
2. „Verfügbar ab: 06.11.2026“ → Vorbestellung bzw. bald verfügbar
3. Lieferstatus-Ampel: status-2 (grün) / status-1 (knapp) = bestellbar, status-0 = ausverkauft
Passt nichts davon, heißt das Ergebnis UNBEKANNT – lieber ehrlich als falsch geraten.

Wichtig: Auf Produktseiten stehen auch Empfehlungen („Kunden kauften auch“) mit
eigenen Preisen. Die liegen in verschachtelten Produkt-Blöcken und werden übersprungen.
"""

from __future__ import annotations

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


class JtlShop(ShopAdapter):
    def __init__(self, name: str, domains: tuple[str, ...]):
        self.name = name
        self.domains = domains

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

        termin = datum_aus_text(termin_el.get_text(" ") if termin_el else None)
        status = _status(
            schema=schema_status(_wert(verfuegbarkeit)),
            klassen=_klassen(lieferstatus),
            termin=termin,
            heute=heute,
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
            status = _status(
                schema=schema_status(_wert(box.select_one("[itemprop=availability]"))),
                klassen=_klassen(lieferstatus),
                termin=termin,
                heute=heute,
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

def _status(schema: Status | None, klassen: set[str], termin: date | None, heute: date) -> Status:
    """Entscheidet den Status aus allen Hinweisen der Seite."""
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
    return Status.UNBEKANNT


def _eigenes(haupt: Tag, auswahl: str) -> Tag | None:
    """Erstes passendes Element, das NICHT zu einem verschachtelten Produkt (Empfehlung) gehört."""
    for el in haupt.select(auswahl):
        besitzer = el.find_parent(attrs={"itemtype": lambda t: t and "schema.org/Product" in t})
        if besitzer is haupt:
            return el
    return None


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
