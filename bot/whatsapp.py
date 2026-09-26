"""Schickt WhatsApp-Nachrichten an dich – über den kostenlosen Dienst CallMeBot.

Einrichtung: siehe ANLEITUNG_IPHONE.md, Schritt 1.

Gut zu wissen:
- CallMeBot kann dir nur SCHREIBEN. Buttons gibt es nicht, Links in der
  Nachricht kannst du aber antippen.
- Limit: höchstens 25 Nachrichten in 4 Stunden. Deshalb fasst der Bot
  alle Neuigkeiten eines Laufs in EINER Nachricht zusammen.
- Formatierung wie in WhatsApp: *fett*, _kursiv_
"""

from __future__ import annotations

import re

import requests

API_URL = "https://api.callmebot.com/whatsapp.php"


class WhatsAppFehler(Exception):
    """CallMeBot hat die Nachricht nicht angenommen oder war nicht erreichbar."""


def pruefe_nummer(nummer: str) -> str:
    """Macht aus '+49 170 1234567' oder '0049 170-1234567' die Form '+491701234567'."""
    sauber = re.sub(r"[\s\-/()]", "", nummer)
    if sauber.startswith("00"):
        sauber = "+" + sauber[2:]
    if not re.fullmatch(r"\+\d{8,15}", sauber):
        raise WhatsAppFehler(
            "Die WhatsApp-Nummer muss mit Ländervorwahl anfangen, z. B. +49 170 1234567 "
            "(also +49 statt der ersten 0). Prüfe das Secret WHATSAPP_NUMMER."
        )
    return sauber


class WhatsApp:
    def __init__(self, nummer: str, apikey: str, timeout: float = 30):
        if not nummer or not apikey:
            raise WhatsAppFehler("Es fehlen die Secrets WHATSAPP_NUMMER und/oder CALLMEBOT_APIKEY.")
        self._nummer = pruefe_nummer(nummer)
        self._apikey = apikey.strip()
        self._timeout = timeout

    def sende(self, text: str) -> None:
        """Schickt eine Nachricht. Wirft WhatsAppFehler, wenn es nicht geklappt hat."""
        parameter = {"phone": self._nummer, "text": text, "apikey": self._apikey}
        try:
            antwort = requests.get(API_URL, params=parameter, timeout=self._timeout)
        except requests.RequestException as fehler:
            # Wichtig: Die Original-Fehlermeldung enthält die Adresse MIT API-Key und Nummer.
            # Deshalb geben wir nur die Art des Fehlers weiter ("from None").
            raise WhatsAppFehler(
                f"CallMeBot ist gerade nicht erreichbar ({type(fehler).__name__})."
            ) from None

        inhalt = self._schwaerze(_nur_text(antwort.text))
        # CallMeBot meldet auch Fehler mit HTTP 200. Deshalb zählt nur „Message queued“
        # als Erfolg – lieber ein Fehler zu viel als ein verschluckter Ping.
        if antwort.status_code == 200 and "message queued" in inhalt.lower():
            return
        raise WhatsAppFehler(_erklaere(antwort.status_code, inhalt))

    def _schwaerze(self, text: str) -> str:
        """Ersetzt API-Key und Nummer durch *** (die Protokolle sind öffentlich)."""
        for geheim in (self._apikey, self._nummer, self._nummer.lstrip("+")):
            text = text.replace(geheim, "***")
        return text


def _nur_text(html: str) -> str:
    """CallMeBot antwortet mit einer kleinen HTML-Seite – wir brauchen nur den Text."""
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())[:300]


def _erklaere(status_code: int, inhalt: str) -> str:
    """Übersetzt typische CallMeBot-Antworten in verständliches Deutsch."""
    klein = inhalt.lower()
    if "limit" in klein:
        return ("CallMeBot-Limit erreicht: höchstens 25 Nachrichten in 4 Stunden. "
                "Später klappt es wieder.")
    if "apikey" in klein or "api key" in klein:
        return f"CallMeBot lehnt den API-Key ab. Prüfe das Secret CALLMEBOT_APIKEY. (Antwort: {inhalt})"
    return (f"CallMeBot hat die Nachricht nicht angenommen (HTTP {status_code}). "
            f"Antwort: {inhalt or 'leer'}")
