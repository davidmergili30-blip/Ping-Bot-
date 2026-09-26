"""Startpunkt des Bots.

Aufruf:  python -m bot <aktion>

Aktionen:
  normaler-lauf   – der regelmäßige Lauf (alle 15 Minuten über GitHub Actions)
  test-nachricht  – schickt eine Test-Nachricht per WhatsApp an dein iPhone
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from bot.einstellungen import ConfigFehler, Einstellungen, lade_einstellungen
from bot.whatsapp import WhatsApp, WhatsAppFehler

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
    except WhatsAppFehler as fehler:
        log.error("%s", fehler)
        return 1


def normaler_lauf(einstellungen: Einstellungen) -> int:
    log.info("Normaler Lauf gestartet.")
    log.info(
        "Watchlist: %d Produkt(e), vertrauenswürdige Shops: %d",
        len(einstellungen.watchlist),
        len(einstellungen.vertrauenswuerdige_shops),
    )
    if not (_geheimnis("WHATSAPP_NUMMER") and _geheimnis("CALLMEBOT_APIKEY")):
        log.warning("WhatsApp ist noch nicht fertig eingerichtet (Secrets fehlen). Siehe ANLEITUNG_IPHONE.md")
    log.info("Die Shop-Checks kommen in Phase 2. Bis dahin gibt es nichts zu tun.")
    return 0


def test_nachricht(einstellungen: Einstellungen) -> int:
    nummer = _geheimnis("WHATSAPP_NUMMER")
    apikey = _geheimnis("CALLMEBOT_APIKEY")
    if not nummer or not apikey:
        log.error(
            "Für die Test-Nachricht brauchst du beide Secrets: WHATSAPP_NUMMER und "
            "CALLMEBOT_APIKEY. Siehe ANLEITUNG_IPHONE.md, Schritt 2."
        )
        return 1

    jetzt = datetime.now(ZoneInfo(einstellungen.allgemein.zeitzone))
    text = (
        "✅ *Dein Pokémon-Preis-Bot läuft!*\n"
        f"Test gestartet am {jetzt:%d.%m.%Y} um {jetzt:%H:%M} Uhr.\n\n"
        "Wenn du das liest, ist Phase 1 geschafft. 🎉"
    )
    link = _github_link()
    if link:
        text += f"\n\n👉 GitHub: {link}"

    WhatsApp(nummer, apikey).sende(text)
    log.info("Test-Nachricht wurde an CallMeBot übergeben. Sie kommt in ein paar Sekunden auf deinem iPhone an.")
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
