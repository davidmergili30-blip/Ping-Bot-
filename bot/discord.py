"""Schickt Nachrichten in einen Kanal auf deinem Discord-Server – über einen Webhook.

Ein Webhook ist ein geheimer Link zu genau einem Kanal. Wer den Link kennt,
kann dort Nachrichten posten. Deshalb gehört er NUR in die GitHub Secrets.
Einrichtung: siehe ANLEITUNG_IPHONE.md.

Jede Neuigkeit wird ein eigener „Kasten“ (bei Discord heißt das Embed) mit
farbigem Rand und antippbarem Titel, der direkt zum Shop führt.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

WEBHOOK_MUSTER = re.compile(r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")

# Grenzen von Discord pro Nachricht
MAX_KAESTEN = 10
MAX_ZEICHEN = 5500  # Discord erlaubt 6000 – wir lassen etwas Luft


class DiscordFehler(Exception):
    """Discord hat die Nachricht nicht angenommen oder war nicht erreichbar."""


@dataclass
class Kasten:
    """Ein Kasten in der Discord-Nachricht, z. B. ein Ping für ein Produkt."""

    titel: str
    text: str = ""
    link: str | None = None   # Titel wird antippbar und öffnet diesen Link
    farbe: int | None = None  # Randfarbe, z. B. 0x2ECC71 für Grün
    art: str = "info"         # "kaufbar", "einladung" oder "info" – jede Art kommt als eigene Nachricht

    def als_embed(self) -> dict:
        embed = {"title": self.titel[:256], "description": self.text[:4000]}
        if self.link:
            embed["url"] = self.link
        if self.farbe is not None:
            embed["color"] = self.farbe
        return embed

    def laenge(self) -> int:
        return len(self.titel[:256]) + len(self.text[:4000])


class DiscordWebhook:
    NAME = "Pokémon-Preis-Bot"

    def __init__(self, webhook_url: str, timeout: float = 20, schlafen=time.sleep):
        url = (webhook_url or "").strip().split("?")[0]
        if not url:
            raise DiscordFehler("Es fehlt das Secret DISCORD_WEBHOOK_URL.")
        if not WEBHOOK_MUSTER.match(url):
            raise DiscordFehler(
                "DISCORD_WEBHOOK_URL sieht nicht wie ein Discord-Webhook aus. "
                "Er muss mit https://discord.com/api/webhooks/ anfangen."
            )
        self._url = url
        self._timeout = timeout
        self._schlafen = schlafen

    def sende(self, text: str = "", kaesten: list[Kasten] | None = None) -> None:
        """Schickt eine Nachricht. Viele Kästen werden auf mehrere Nachrichten verteilt."""
        pakete = _in_pakete(kaesten or [])
        for nr, paket in enumerate(pakete):
            daten = {
                "username": self.NAME,
                "content": text[:2000] if nr == 0 else "",
                "embeds": [k.als_embed() for k in paket],
                # Niemanden versehentlich anpingen (z. B. @everyone aus Shop-Texten)
                "allowed_mentions": {"parse": []},
            }
            self._post(daten)

    def _post(self, daten: dict, versuch: int = 1) -> None:
        try:
            antwort = requests.post(self._url, json=daten, params={"wait": "true"}, timeout=self._timeout)
        except requests.RequestException as fehler:
            # Wichtig: Die Original-Fehlermeldung enthält den geheimen Webhook-Link.
            # Deshalb geben wir nur die Art des Fehlers weiter ("from None").
            raise DiscordFehler(f"Discord ist gerade nicht erreichbar ({type(fehler).__name__}).") from None

        if antwort.status_code in (200, 204):
            return
        if antwort.status_code == 429 and versuch == 1:
            # Zu viele Nachrichten auf einmal: kurz warten und einmal nochmal versuchen
            self._schlafen(min(_warte_sekunden(antwort), 10))
            return self._post(daten, versuch=2)
        raise DiscordFehler(_erklaere(antwort))


def _in_pakete(kaesten: list[Kasten]) -> list[list[Kasten]]:
    """Verteilt die Kästen so, dass keine Nachricht die Grenzen von Discord sprengt."""
    pakete: list[list[Kasten]] = [[]]
    zeichen = 0
    for kasten in kaesten:
        if len(pakete[-1]) >= MAX_KAESTEN or (pakete[-1] and zeichen + kasten.laenge() > MAX_ZEICHEN):
            pakete.append([])
            zeichen = 0
        pakete[-1].append(kasten)
        zeichen += kasten.laenge()
    return pakete


def _warte_sekunden(antwort) -> float:
    try:
        return float(antwort.json().get("retry_after", 2))
    except (ValueError, AttributeError):
        return 2.0


def _erklaere(antwort) -> str:
    """Übersetzt typische Discord-Fehler in verständliches Deutsch."""
    if antwort.status_code in (401, 404):
        return ("Der Webhook-Link ist ungültig oder wurde gelöscht. Leg in Discord einen neuen an "
                "und ändere das Secret DISCORD_WEBHOOK_URL.")
    if antwort.status_code == 429:
        return "Discord bremst gerade (zu viele Nachrichten). Beim nächsten Lauf klappt es wieder."
    try:
        details = antwort.json().get("message", "")
    except ValueError:
        details = ""
    return f"Discord hat die Nachricht abgelehnt (HTTP {antwort.status_code}). {details}".strip()
