"""Lädt Shop-Seiten herunter – höflich und ehrlich.

- prüft vorher die robots.txt (verbotene Seiten werden NICHT abgerufen)
- ehrlicher User-Agent aus config.yaml, kein Vortäuschen eines Browsers
- Pause zwischen zwei Anfragen an denselben Shop
- erkennt Sperren (403, 429, Captcha, Cloudflare & Co.) und umgeht sie NICHT:
  der Status wird dann UNBEKANNT und du bekommst einmalig Bescheid
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass

import requests

from bot.adapter.basis import domain_von

# Typische Kennzeichen von Bot-Schutz-Seiten (nur eindeutige – normale Shopseiten
# erwähnen z. B. oft „captcha“ im Kontaktformular)
SPERR_MERKMALE = (
    "challenge-platform",
    "cf-chl-",
    "<title>just a moment",
    "attention required! | cloudflare",
    "px-captcha",
    "_incapsula_resource",
    "pardon our interruption",
)


@dataclass
class Seite:
    url: str
    text: str | None = None
    http: int | None = None
    problem: str | None = None  # warum es keinen Inhalt gibt
    gesperrt: bool = False      # True = Shop blockt den Bot oder verbietet den Abruf


class Abrufer:
    def __init__(self, user_agent: str, pause_sekunden: float, sitzung=None,
                 schlafen=time.sleep, uhr=time.monotonic):
        self._kopf = {"User-Agent": user_agent, "Accept-Language": "de-DE,de;q=0.9"}
        self._user_agent = user_agent
        self._pause = pause_sekunden
        self._sitzung = sitzung or requests.Session()
        self._schlafen = schlafen
        self._uhr = uhr
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._letzte_anfrage: dict[str, float] = {}

    def hole(self, url: str) -> Seite:
        erlaubt = self._robots_erlaubt(url)
        if erlaubt is None:
            return Seite(url, problem="robots.txt nicht erreichbar – zur Sicherheit nicht abgerufen")
        if not erlaubt:
            return Seite(url, problem="robots.txt verbietet den Abruf", gesperrt=True)

        try:
            antwort = self._anfrage(url)
        except requests.RequestException as fehler:
            return Seite(url, problem=f"nicht erreichbar ({type(fehler).__name__})")

        grund = sperre_erkennen(antwort)
        if grund:
            return Seite(url, http=antwort.status_code, problem=grund, gesperrt=True)
        if antwort.status_code == 404:
            return Seite(url, http=404, problem="Seite nicht gefunden (404) – ist der Link noch richtig?")
        if antwort.status_code >= 400:
            return Seite(url, http=antwort.status_code, problem=f"Fehler vom Shop (HTTP {antwort.status_code})")
        return Seite(url, text=antwort.text, http=antwort.status_code)

    def _anfrage(self, url: str):
        """Eine Anfrage mit Pause zum vorherigen Abruf beim selben Shop."""
        domain = domain_von(url)
        letzte = self._letzte_anfrage.get(domain)
        if letzte is not None:
            rest = self._pause - (self._uhr() - letzte)
            if rest > 0:
                self._schlafen(rest)
        try:
            return self._sitzung.get(url, headers=self._kopf, timeout=30)
        finally:
            self._letzte_anfrage[domain] = self._uhr()

    def _robots_erlaubt(self, url: str) -> bool | None:
        """True/False laut robots.txt – None, wenn sie nicht zu bekommen war."""
        teile = urllib.parse.urlsplit(url)
        basis = f"{teile.scheme}://{teile.netloc}"
        if basis not in self._robots:
            self._robots[basis] = self._lade_robots(basis)
        regeln = self._robots[basis]
        return None if regeln is None else regeln.can_fetch(self._user_agent, url)

    def _lade_robots(self, basis: str) -> urllib.robotparser.RobotFileParser | None:
        regeln = urllib.robotparser.RobotFileParser()
        try:
            antwort = self._anfrage(basis + "/robots.txt")
        except requests.RequestException:
            return None
        if antwort.status_code == 200:
            regeln.parse(antwort.text.splitlines())
        elif antwort.status_code in (401, 403):
            regeln.disallow_all = True   # Zugriff verweigert → lieber gar nicht
        elif 400 <= antwort.status_code < 500:
            regeln.allow_all = True      # keine robots.txt vorhanden → alles erlaubt
        else:
            return None                  # Serverfehler → diesmal nicht abrufen
        return regeln


def sperre_erkennen(antwort) -> str | None:
    """Gibt den Grund zurück, wenn die Antwort nach einer Sperre aussieht."""
    ziel = domain_von(getattr(antwort, "url", "") or "")
    if ziel.startswith("banned."):
        return "Shop hat den Bot gesperrt (Weiterleitung auf eine Sperrseite)"
    if antwort.status_code == 403:
        return "Seite blockt den Bot (HTTP 403)"
    if antwort.status_code == 429:
        return "Shop meldet zu viele Anfragen (HTTP 429)"
    anfang = (antwort.text or "")[:30000].lower()
    if any(merkmal in anfang for merkmal in SPERR_MERKMALE):
        return f"Bot-Schutz / Captcha erkannt (HTTP {antwort.status_code})"
    return None
