"""Startpunkt des Bots.

Aufruf:  python -m bot <aktion> [--name …] [--suchbegriffe …] [--preis …]

Aktionen (in der GitHub-App unter Actions → Preis-Bot → Run workflow):
  normaler-lauf    – alle Sets und Kategorien prüfen (läuft auch automatisch)
  status           – letzter Lauf, blockierte Shops, was gerade verfügbar ist
  watchlist        – deine Sets mit Suchbegriffen und Maximalpreisen anzeigen
  set-hinzufuegen  – neues Set beobachten (--name, optional --suchbegriffe)
  set-entfernen    – Set nicht mehr beobachten (--name)
  max-preis        – Maximalpreis für ein Set setzen (--name, --preis; „aus“ = keiner)
  pause / weiter   – alle Prüfungen und Pings anhalten / wieder starten
  test-nachricht   – schickt eine Test-Nachricht in deinen Discord-Kanal
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from bot.abruf import Abrufer
from bot.adapter import ADAPTER
from bot.discord import DiscordFehler, DiscordWebhook, Kasten
from bot.einstellungen import STANDARD_PFAD as CONFIG_PFAD
from bot.einstellungen import ConfigFehler, Einstellungen, lade_einstellungen
from bot.lauf import Lauf
from bot.pings import EMOJI, FARBE_INFO, euro
from bot.speicher import STANDARD_PFAD, Speicher
from bot.status import Status
from bot.steuerung import ConfigBearbeiter, SteuerFehler, beschreibe_max_preis, preis_aus_eingabe

log = logging.getLogger("bot")

AKTIONEN = ("normaler-lauf", "status", "watchlist", "set-hinzufuegen", "set-entfernen", "max-preis",
            "pause", "weiter", "test-nachricht")
AENDERN = {"set-hinzufuegen", "set-entfernen", "max-preis", "pause", "weiter"}

GRUEN, ROT = 0x2ECC71, 0xE74C3C
MAX_ZEILEN = 20


def main(argv: list[str] | None = None) -> int:
    """Führt eine Aktion aus. Gibt 0 zurück, wenn alles geklappt hat, sonst 1."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    # Liest eine lokale .env-Datei, falls vorhanden (nur für Tests am Computer).
    # Auf GitHub kommen die Werte aus den Secrets.
    load_dotenv()

    parser = argparse.ArgumentParser(prog="python -m bot", description="Pokémon-TCG Preis- & Restock-Bot")
    parser.add_argument("aktion", nargs="?", default="normaler-lauf", choices=AKTIONEN)
    parser.add_argument("--name", default="", help="Set-Name")
    parser.add_argument("--suchbegriffe", default="", help="weitere Suchbegriffe, mit Komma getrennt")
    parser.add_argument("--preis", default="", help="Maximalpreis in Euro oder „aus“")
    args = parser.parse_args(argv)
    config_pfad = Path(os.environ.get("BOT_CONFIG") or CONFIG_PFAD)

    try:
        einstellungen = lade_einstellungen(config_pfad)
    except ConfigFehler as fehler:
        log.error("Fehler in config.yaml: %s", fehler)
        return 1

    try:
        if args.aktion == "test-nachricht":
            return test_nachricht(einstellungen)
        if args.aktion in AENDERN:
            return aendern(args, config_pfad)
        if args.aktion == "status":
            return status(einstellungen)
        if args.aktion == "watchlist":
            return watchlist(einstellungen)
        return normaler_lauf(einstellungen)
    except DiscordFehler as fehler:
        log.error("%s", fehler)
        return 1


# --- Normaler Lauf --------------------------------------------------------------------------

def normaler_lauf(einstellungen: Einstellungen) -> int:
    if einstellungen.allgemein.pausiert:
        log.info("Der Bot ist pausiert – es wird nichts geprüft. Weiter geht es mit der Aktion „weiter“.")
        return 0
    melder = _melder()
    if melder is None:
        log.warning("Discord ist noch nicht fertig eingerichtet (Secret fehlt). Siehe ANLEITUNG_IPHONE.md")
    speicher = _speicher()
    abrufer = Abrufer(
        einstellungen.allgemein.user_agent,
        einstellungen.allgemein.pause_zwischen_anfragen_sekunden,
        robots_beachten=einstellungen.allgemein.robots_txt_beachten,
        pausen={d: a.min_abstand_sekunden for a in ADAPTER if a.min_abstand_sekunden for d in a.abruf_domains()},
    )
    try:
        return Lauf(
            einstellungen, speicher, abrufer, melder,
            jetzt=datetime.now(timezone.utc),
            heute=datetime.now(ZoneInfo(einstellungen.allgemein.zeitzone)).date(),
        ).starten()
    finally:
        speicher.schliessen()


# --- Steuerung: config.yaml ändern ---------------------------------------------------------

def aendern(args, config_pfad: Path) -> int:
    try:
        bearbeiter = ConfigBearbeiter(config_pfad)
        kasten = _fuehre_aus(bearbeiter, args)
        bearbeiter.speichern()
    except SteuerFehler as fehler:
        log.error("%s", fehler)
        _schicke(Kasten(titel=f"❌ {args.aktion} hat nicht geklappt", text=str(fehler), farbe=ROT))
        return 1
    log.info("%s: %s", kasten.titel, kasten.text.replace("\n", " | "))
    _schicke(kasten)
    return 0


def _fuehre_aus(bearbeiter: ConfigBearbeiter, args) -> Kasten:
    sofort = "\nSofort prüfen: Actions → Preis-Bot → Run workflow → normaler-lauf"
    if args.aktion == "set-hinzufuegen":
        begriffe = [b.strip() for b in args.suchbegriffe.split(",") if b.strip()]
        eintrag = bearbeiter.set_hinzufuegen(args.name, begriffe)
        return Kasten(
            titel=f"✅ Set hinzugefügt: {eintrag['name']}",
            text=f"Suchbegriffe: {', '.join(eintrag['suche'])}\n"
                 f"Beim nächsten Lauf bekommst du eine Übersicht pro Shop.{sofort}",
            farbe=GRUEN)
    if args.aktion == "set-entfernen":
        eintrag = bearbeiter.set_entfernen(args.name)
        return Kasten(titel=f"🗑️ Set entfernt: {eintrag['name']}",
                      text="Der Bot beobachtet dieses Set nicht mehr.", farbe=FARBE_INFO)
    if args.aktion == "max-preis":
        preis = preis_aus_eingabe(args.preis)
        eintrag = bearbeiter.max_preis(args.name, preis)
        if preis is None:
            return Kasten(titel=f"💶 Maximalpreis aufgehoben: {eintrag['name']}",
                          text="Du bekommst wieder Pings, egal wie teuer.", farbe=FARBE_INFO)
        return Kasten(titel=f"💶 Maximalpreis für {eintrag['name']}: {euro(preis)}",
                      text=f"Produkte dieses Sets über {euro(preis)} lösen keinen Ping mehr aus.\n"
                           "Fällt ein Preis unter diese Grenze, bekommst du Bescheid.", farbe=GRUEN)
    if args.aktion == "pause":
        bearbeiter.pause(True)
        return Kasten(titel="⏸️ Bot pausiert",
                      text="Er prüft nichts und schickt keine Pings, bis du „weiter“ auswählst.", farbe=FARBE_INFO)
    if args.aktion != "weiter":
        raise SteuerFehler(f"Unbekannte Aktion: {args.aktion}")
    bearbeiter.pause(False)
    return Kasten(titel="▶️ Bot läuft wieder", text=f"Ab dem nächsten Lauf wird wieder geprüft.{sofort}",
                  farbe=GRUEN)


# --- Steuerung: nur anzeigen ---------------------------------------------------------------

def watchlist(einstellungen: Einstellungen) -> int:
    zeilen = []
    for produkt in einstellungen.watchlist:
        teile = []
        if produkt.suche:
            teile.append("Suche: " + ", ".join(produkt.suche))
        if produkt.links:
            teile.append(f"{len(produkt.links)} Link(s)")
        teile.append(beschreibe_max_preis({"max_preis": produkt.regeln.max_preis}))
        zeilen.append(f"**{produkt.name}** – " + " · ".join(teile))
    if not zeilen:
        zeilen.append("Die Watchlist ist leer. Neues Set: Run workflow → set-hinzufuegen")
    zeilen.append("")
    zeilen.append("**Kategorien:** " + (", ".join(k.name for k in einstellungen.kategorien) or "keine"))
    zeilen.append("**Pingt bei:** " + ", ".join(s.value for s in einstellungen.standard_regeln.ping_bei_status))
    if einstellungen.allgemein.pausiert:
        zeilen.append("⏸️ **Der Bot ist gerade pausiert.**")
    _schicke(Kasten(titel=f"📋 Deine Watchlist ({len(einstellungen.watchlist)} Einträge)",
                    text="\n".join(zeilen), farbe=FARBE_INFO))
    log.info("Watchlist an Discord geschickt.")
    return 0


def status(einstellungen: Einstellungen) -> int:
    speicher = _speicher()
    try:
        zone = ZoneInfo(einstellungen.allgemein.zeitzone)
        letzter = speicher.meta("letzter_lauf")
        zeilen = [
            "⏸️ **Pausiert**" if einstellungen.allgemein.pausiert else "▶️ **Aktiv**",
            "Letzter Lauf: " + (f"{datetime.fromisoformat(letzter).astimezone(zone):%d.%m.%Y um %H:%M} Uhr"
                                if letzter else "noch keiner"),
            f"Watchlist: {len(einstellungen.watchlist)} Einträge · Kategorien: {len(einstellungen.kategorien)}",
        ]
        blockiert = speicher.blockierte()
        if blockiert:
            zeilen.append("⚠️ Blockierte Shops: " + "; ".join(f"{b['domain']} ({b['grund']})" for b in blockiert))
        else:
            zeilen.append("✅ Kein Shop blockt den Bot.")

        verfuegbar = speicher.verfuegbare(einstellungen.standard_regeln.ping_bei_status)
        zeilen.append("")
        zeilen.append(f"**Gerade verfügbar ({len(verfuegbar)}):**" if verfuegbar
                      else "**Gerade ist nichts Passendes verfügbar.**")
        for zeile in verfuegbar[:MAX_ZEILEN]:
            zeilen.append(f"{EMOJI.get(_status_von(zeile['status']), '•')} [{zeile['produkt']}]({zeile['url']}) – "
                          f"{euro(zeile['preis'])} ({zeile['shop']})")
        if len(verfuegbar) > MAX_ZEILEN:
            zeilen.append(f"… und {len(verfuegbar) - MAX_ZEILEN} weitere")
    finally:
        speicher.schliessen()
    _schicke(Kasten(titel="📊 Status", text="\n".join(zeilen), farbe=FARBE_INFO))
    log.info("Status an Discord geschickt.")
    return 0


# --- Test-Nachricht --------------------------------------------------------------------------

def test_nachricht(einstellungen: Einstellungen) -> int:
    melder = _melder()
    if melder is None:
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
        farbe=GRUEN,
    )
    melder.sende(kaesten=[kasten])
    log.info("Test-Nachricht wurde an Discord geschickt. Schau in deinen Kanal!")
    return 0


# --- Hilfen -----------------------------------------------------------------------------------

def _melder() -> DiscordWebhook | None:
    webhook = _geheimnis("DISCORD_WEBHOOK_URL")
    return DiscordWebhook(webhook) if webhook else None


def _schicke(kasten: Kasten) -> None:
    """Schickt eine Antwort in den Discord-Kanal (ohne Discord nur ins Protokoll)."""
    melder = _melder()
    if melder is None:
        log.warning("Discord ist nicht eingerichtet – Antwort nur hier im Protokoll: %s", kasten.titel)
        return
    melder.sende(text=kasten.titel, kaesten=[kasten])


def _speicher() -> Speicher:
    return Speicher(os.environ.get("BOT_DATENBANK") or STANDARD_PFAD)


def _status_von(wert: str) -> Status | None:
    try:
        return Status(wert)
    except ValueError:
        return None


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
