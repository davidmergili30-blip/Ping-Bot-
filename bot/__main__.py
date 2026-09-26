"""Startpunkt des Bots.

Aufruf:  python -m bot <aktion>

Aktionen:
  normaler-lauf   – der regelmäßige Lauf (alle 15 Minuten über GitHub Actions)
  test-nachricht  – schickt eine Test-Nachricht in deinen Discord-Kanal
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from bot.discord import DiscordFehler, DiscordWebhook, Kasten
from bot.einstellungen import ConfigFehler, Einstellungen, lade_einstellungen

log = logging.getLogger("bot")

AKTIONEN = ("normaler-lauf", "test-nachricht")


def main(argv: list[str] | None = None) -> int:
    """Führt eine Aktion aus. Gibt 0 zurück, wenn alles geklappt hat, sonst 1."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    # Liest eine lokale .env-Datei, falls vorhanden (nur für Tests am Computer).
    # Auf GitHub kommen die Werte aus den Secrets.
    load_dotenv()

    parser = argparse.ArgumentParser(prog="python -m bot", description="Pokémon-TCG Preis- & Restock-Bot")
    parser.add_argument("aktion", nargs="?", default="normaler-lauf", choices=AKTIONEN)
    args = parser.parse_args(argv)

    try:
        einstellungen = lade_einstellungen()
    except ConfigFehler as fehler:
        log.error("Fehler in config.yaml: %s", fehler)
        return 1

    try:
        if args.aktion == "test-nachricht":
            return test_nachricht(einstellungen)
        return normaler_lauf(einstellungen)
    except DiscordFehler as fehler:
        log.error("%s", fehler)
        return 1


def normaler_lauf(einstellungen: Einstellungen) -> int:
    log.info("Normaler Lauf gestartet.")
    log.info(
        "Watchlist: %d Produkt(e), vertrauenswürdige Shops: %d",
        len(einstellungen.watchlist),
        len(einstellungen.vertrauenswuerdige_shops),
    )
    if not _geheimnis("DISCORD_WEBHOOK_URL"):
        log.warning("Discord ist noch nicht fertig eingerichtet (Secret fehlt). Siehe ANLEITUNG_IPHONE.md")
    log.info("Die Shop-Checks kommen in Phase 2. Bis dahin gibt es nichts zu tun.")
    return 0


def test_nachricht(einstellungen: Einstellungen) -> int:
    webhook = _geheimnis("DISCORD_WEBHOOK_URL")
    if not webhook:
        log.error("Für die Test-Nachricht brauchst du das Secret DISCORD_WEBHOOK_URL. Siehe ANLEITUNG_IPHONE.md")
        return 1

    jetzt = datetime.now(ZoneInfo(einstellungen.allgemein.zeitzone))
    kasten = Kasten(
        titel="✅ Dein Pokémon-Preis-Bot läuft!",
        text=(
            f"Test gestartet am {jetzt:%d.%m.%Y} um {jetzt:%H:%M} Uhr.\n\n"
            "Wenn du das liest, klappt die Verbindung zu Discord. 🎉"
            + ("\nTipp auf die Überschrift, um GitHub zu öffnen." if _github_link() else "")
        ),
        link=_github_link(),
        farbe=0x2ECC71,
    )
    DiscordWebhook(webhook).sende(kaesten=[kasten])
    log.info("Test-Nachricht wurde an Discord geschickt. Schau in deinen Kanal!")
    return 0


def _geheimnis(name: str) -> str:
    """Liest ein Secret aus den Umgebungsvariablen (leer, wenn es fehlt)."""
    return os.environ.get(name, "").strip()


def _github_link() -> str | None:
    """Link zur Actions-Seite des Repos (gibt es nur, wenn der Bot auf GitHub läuft)."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    return f"{server}/{repo}/actions" if server and repo else None


if __name__ == "__main__":
    sys.exit(main())
