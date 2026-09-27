"""Gemeinsame Bausteine für alle Shop-Adapter.

Ein Adapter „übersetzt“ die Seite eines Shops in ein einheitliches Ergebnis.
Er lädt selbst nichts herunter – das macht bot/abruf.py. So kann man jeden
Adapter mit gespeicherten Beispielseiten testen (siehe tests/beispiele/).
"""

from __future__ import annotations

import re
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from bot.status import Status

DATUM_MUSTER = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


@dataclass
class CheckErgebnis:
    status: Status
    preis: float | None = None
    titel: str | None = None
    verkaeufer: str | None = None     # "Shop" oder Name des Drittanbieters
    versand: float | None = None
    mengenlimit: int | None = None
    liefertermin: str | None = None   # z. B. "06.11.2026" bei Vorbestellungen
    hinweis: str | None = None        # z. B. warum der Status UNBEKANNT ist


@dataclass
class ListenEintrag:
    """Ein Produkt auf einer Kategorieseite."""

    url: str
    ergebnis: CheckErgebnis


class ShopAdapter(ABC):
    name: str
    domains: tuple[str, ...]
    treffer_pro_seite: int = 0  # 0 = dieser Shop kann (noch) nicht durchsucht werden
    min_abstand_sekunden: float = 0  # > 0 = längere Pause zwischen Anfragen (Wunsch des Shops)

    def abruf_domains(self) -> tuple[str, ...]:
        """Adressen, von denen tatsächlich geladen wird (kann von der Shop-Adresse abweichen)."""
        return self.domains

    def passt_zu(self, url: str) -> bool:
        return domain_von(url) in self.domains

    def such_url(self, begriff: str, seite: int = 1) -> str | None:
        """Adresse der Suchergebnisse im Shop – oder None, wenn Suchen nicht geht."""
        return None

    @abstractmethod
    def erkenne_produkt(self, html: str, url: str, heute: date | None = None) -> CheckErgebnis:
        """Liest den Status eines einzelnen Produkts aus seiner Produktseite."""

    @abstractmethod
    def erkenne_liste(self, html: str, url: str, heute: date | None = None) -> list[ListenEintrag]:
        """Liest alle Produkte einer Kategorieseite."""


def domain_von(url: str) -> str:
    """'https://www.card-corner.de/xyz' -> 'card-corner.de'"""
    return (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")


def ohne_anker(url: str) -> str:
    """Entfernt '#tab-votes' und Ähnliches am Ende eines Links."""
    return urllib.parse.urldefrag(url)[0]


def schema_status(wert: str | None) -> Status | None:
    """Übersetzt schema.org-Verfügbarkeiten (z. B. 'https://schema.org/PreOrder')."""
    if not wert:
        return None
    name = wert.rstrip("/").rsplit("/", 1)[-1].lower()
    return {
        "instock": Status.BESTELLBAR,
        "limitedavailability": Status.BESTELLBAR,
        "onlineonly": Status.BESTELLBAR,
        "preorder": Status.VORBESTELLBAR,
        "presale": Status.VORBESTELLBAR,
        "outofstock": Status.AUSVERKAUFT,
        "soldout": Status.AUSVERKAUFT,
        "discontinued": Status.AUSVERKAUFT,
        "instoreonly": Status.NUR_FILIALE,
    }.get(name)


def preis_als_zahl(text: str | None) -> float | None:
    """'199.90', '199,90 €' oder '1.234,56 €' -> Zahl. Unklares -> None."""
    if not text:
        return None
    sauber = re.sub(r"[^\d.,]", "", text)
    if not sauber:
        return None
    if "," in sauber:
        # Deutsches Format: Punkt = Tausender, Komma = Dezimal
        sauber = sauber.replace(".", "").replace(",", ".")
    try:
        zahl = round(float(sauber), 2)
    except ValueError:
        return None
    # 0 € heißt bei Vorbestellungen oft „Preis steht noch nicht fest“
    return zahl if zahl > 0 else None


def datum_aus_text(text: str | None) -> date | None:
    """Findet das erste Datum wie '06.11.2026' in einem Text."""
    treffer = DATUM_MUSTER.search(text or "")
    if not treffer:
        return None
    tag, monat, jahr = (int(x) for x in treffer.groups())
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None
