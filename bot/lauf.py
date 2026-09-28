"""Der normale Lauf (alle 15 Minuten): Produkte und Kategorien prüfen, Änderungen melden.

Ablauf:
1. Watchlist: feste Produkt-Links prüfen und Suchbegriffe (z. B. Set-Namen) in allen
   unterstützten Shops suchen – jedes passende Produkt wird beobachtet
2. Jede überwachte Kategorie nach neuen Produkten und Vorbestellungen durchsuchen
3. Deal-Feeds (mydealz) nach neuen Deals durchsehen
4. Neuigkeiten gebündelt schicken – getrennt nach Art: Kaufbares, Einladungen, Infos

Wichtig: Der neue Stand wird erst gespeichert, wenn die Nachricht wirklich
angekommen ist. Klappt der Versand nicht, versucht es der nächste Lauf nochmal –
so geht kein Ping verloren.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta
from functools import partial
from zoneinfo import ZoneInfo

from bot.abruf import Abrufer, Seite
from bot.adapter import ADAPTER, NICHT_ERLAUBT, adapter_fuer
from bot.adapter.basis import CheckErgebnis, ListenEintrag, domain_von
from bot.discord import DiscordWebhook, Kasten
from bot.feeds import Deal, FeedFehler, lies_rss
from bot.einstellungen import Einstellungen, Kategorie, Produkt, Regeln
from bot.produkte import (produktart, regeln_fuer, set_fuer, set_name_aus_titel, vereinfacht,
                          vergleichs_schluessel)
from bot.pings import (EMOJI, FARBE_CHASE, FARBE_INFO, FARBE_WARNUNG, als_link, euro, ist_chase, nach_art,
                       ping_grund, ping_kasten,
                       preis_text)
from bot.speicher import Speicher
from bot.status import Status

log = logging.getLogger("bot")


def enthaelt_wort(text: str | None, wort: str) -> bool:
    """True, wenn 'wort' als eigenes Wort im Text steht (Groß-/Kleinschreibung egal)."""
    return re.search(rf"(?<!\w){re.escape(wort)}(?!\w)", text or "", re.IGNORECASE) is not None

MAX_ZEILEN_UEBERSICHT = 10
VERGLEICH_STATUS = (Status.BESTELLBAR, Status.VORBESTELLBAR)  # was im Preisvergleich als „verfügbar“ zählt
DRINGEND = ("chase", "kaufbar", "einladung")  # Nachrichten, die auch in der Ruhezeit sofort kommen
MAX_SUCHSEITEN = 3   # höchstens so viele Ergebnisseiten pro Suchbegriff und Shop
MAX_NEU_EINZELN = 5  # mehr „neue“ Produkte auf einmal → eine Sammelnachricht statt vieler Pings
MAX_DEALS_EINZELN = 8  # mehr neue Deals auf einmal → Rest als Liste in einem Kasten
TOLERANZ_MINUTEN = 3  # GitHub startet Läufe manchmal etwas zu früh/spät


class Lauf:
    def __init__(self, einstellungen: Einstellungen, speicher: Speicher, abrufer: Abrufer,
                 melder: DiscordWebhook | None, jetzt: datetime, heute: date):
        self.e = einstellungen
        self.speicher = speicher
        self.abrufer = abrufer
        self.melder = melder
        self.jetzt = jetzt
        self.heute = heute
        self.kaesten: list[Kasten] = []
        self.bestaetigungen: list = []  # erst nach erfolgreichem Versand ausführen
        # Was sich der Bot merken soll, SOBALD ein bestimmter Kasten verschickt ist. Hält die Ruhezeit
        # einen Kasten zurück, wird das nicht gemerkt → der nächste Lauf nach der Ruhezeit schickt ihn.
        self._zu_kasten: dict[int, list] = {}
        self._filter_merken: list = []
        self._shop_frei: dict[str, bool] = {}
        self._gesperrt: set[str] = set()
        self._wieder_frei: set[str] = set()
        self._hinweise: set[str] = set()
        self._gesehen: set[str] = set()
        self._watchlist_links = {link for p in self.e.watchlist for link in p.links}
        # Hat sich der Filter geändert (z. B. Mini-Tins dazu)? Dann tauchen in bekannten Listen plötzlich
        # viele „neue“ Produkte auf, die in Wahrheit schon lange da sind → still aufnehmen + EINE Übersicht.
        self._filter_stempel = _stempel(self.e.kategorie_filter.nur_mit, self.e.kategorie_filter.ohne)
        self._filter_geaendert = self.speicher.meta("filter") != self._filter_stempel
        self._durch_filter: list[tuple[ListenEintrag, Produkt | None]] = []
        # Für den Preisvergleich: alle Pings und alles, was in diesem Lauf gesehen wurde
        self._pings: list[tuple[Kasten, str, str | None]] = []
        self._beobachtet: dict[str, tuple[str, str | None, CheckErgebnis]] = {}
        # Neue Sets im Vorverkauf, die (noch) nicht auf der Watchlist stehen: Name → Beispiele
        self._neue_sets: dict[str, list[tuple[str, str | None, str]]] = {}

    def starten(self) -> int:
        log.info("Normaler Lauf: %d Watchlist-Eintrag/-Einträge, %d Kategorie(n)",
                 len(self.e.watchlist), len(self.e.kategorien))
        for produkt in self.e.watchlist:
            for link in produkt.links:
                self._sicher(link, self._pruefe_produkt, produkt, link)
            if produkt.suche:
                self._sicher(f"Suche {produkt.name}", self._pruefe_suche, produkt)
        for kategorie in self.e.kategorien:
            self._sicher(kategorie.name, self._pruefe_kategorie, kategorie)
        for feed in self.e.feeds:
            self._sicher(feed.name, self._pruefe_feed, feed)
        self._preisvergleich()
        self._neue_sets_melden()
        self._filter_uebersicht()
        return self._senden()

    def _sicher(self, quelle: str, pruefen, *args) -> None:
        """Ein unerwarteter Fehler bei EINER Quelle (z. B. völlig kaputte Seite) soll nicht den ganzen
        Lauf stoppen – die anderen Shops werden trotzdem geprüft und gemeldet."""
        try:
            pruefen(*args)
        except Exception:  # noqa: BLE001 – absichtlich breit, der Fehler landet im Protokoll
            log.exception("Unerwarteter Fehler bei %s – diese Quelle wird diesmal übersprungen", quelle)
            self._einmal_melden(f"fehler:{quelle}", Kasten(
                titel=f"⚠️ Fehler beim Prüfen: {quelle}",
                text="Diese Quelle wurde diesmal übersprungen, alles andere läuft normal weiter.\n"
                     "Details stehen im Protokoll des Laufs (Actions → Preis-Bot). Diese Warnung kommt nur einmal.",
                farbe=FARBE_WARNUNG))

    # --- Watchlist: feste Links ----------------------------------------------------

    def _pruefe_produkt(self, produkt: Produkt, url: str) -> None:
        adapter = adapter_fuer(url)
        if adapter is None:
            self._kein_adapter(url)
            return
        seite = self._hole(url)
        if seite is None:
            return
        self._gesehen.add(url)
        if seite.text is None:
            ergebnis = CheckErgebnis(Status.UNBEKANNT, hinweis=seite.problem)
            if seite.http == 404:
                self._einmal_melden(f"defekt:{url}", Kasten(
                    titel=f"⚠️ Link funktioniert nicht – {produkt.name}",
                    text=f"{adapter.name} meldet „Seite nicht gefunden“. Bitte den Link in config.yaml prüfen.",
                    link=url, farbe=FARBE_WARNUNG))
        else:
            ergebnis = adapter.erkenne_produkt(seite.text, url, self.heute)
        self.speicher.speichere_check(url, adapter.name, produkt.name, ergebnis, self.jetzt)
        log.info("%s | %s | %s | %s%s", adapter.name, produkt.name, ergebnis.status.value, euro(ergebnis.preis),
                 f" | {ergebnis.hinweis}" if ergebnis.hinweis else "")
        regeln = self._regeln_fuer(ergebnis.titel, produkt)
        if ergebnis.status != Status.UNBEKANNT:
            self._beobachtet[url] = (adapter.name, ergebnis.titel, ergebnis)
        self._vergleiche(url, adapter.name, produkt.name, ergebnis, regeln, aus_kategorie=False,
                         titel=ergebnis.titel)

    # --- Watchlist: Suchbegriffe (z. B. Set-Namen) ------------------------------------

    def _pruefe_suche(self, produkt: Produkt) -> None:
        """Sucht in jedem unterstützten Shop nach den Begriffen und beobachtet alle Treffer."""
        for adapter in ADAPTER:
            if not adapter.treffer_pro_seite:
                continue
            gefunden: dict[str, ListenEintrag] = {}
            for begriff in produkt.suche:
                for nummer in range(1, MAX_SUCHSEITEN + 1):
                    url = adapter.such_url(begriff, nummer)
                    seite = self._hole(url)
                    if seite is None or seite.text is None:
                        break
                    eintraege = adapter.erkenne_liste(seite.text, url, self.heute)
                    for eintrag in eintraege:
                        # Der Begriff muss im Produktnamen stehen – die Shop-Suche findet sonst auch
                        # Produkte, in deren Beschreibung er nur vorkommt.
                        if enthaelt_wort(eintrag.ergebnis.titel, begriff):
                            gefunden[eintrag.url] = eintrag
                    if len(eintraege) < adapter.treffer_pro_seite:
                        break  # keine weitere Seite
            passende = self._nur_passende(list(gefunden.values()))
            log.info("Suche %s bei %s: %d Treffer mit dem Namen, %d passen zum Filter",
                     produkt.name, adapter.name, len(gefunden), len(passende))
            self._verarbeite(passende, shop=adapter.name, produkt=produkt,
                             schluessel=f"suche:{produkt.name}:{adapter.name}",
                             ueberschrift=f"{produkt.name} bei {adapter.name}", link=adapter.such_url(produkt.suche[0]))

    # --- Kategorien -----------------------------------------------------------------

    def _pruefe_kategorie(self, kategorie: Kategorie) -> None:
        adapter = adapter_fuer(kategorie.link)
        if adapter is None:
            self._kein_adapter(kategorie.link)
            return
        seite = self._hole(kategorie.link)
        if seite is None or seite.text is None:
            if seite is not None:
                log.warning("Kategorie %s: %s", kategorie.name, seite.problem)
            return
        eintraege = adapter.erkenne_liste(seite.text, kategorie.link, self.heute)
        if not eintraege:
            log.warning("Kategorie %s: keine Produkte erkannt – hat der Shop sein Layout geändert?", kategorie.name)
            return
        passende = self._nur_passende(eintraege)
        log.info("Kategorie %s: %d Produkte, %d passen zum Filter", kategorie.name, len(eintraege), len(passende))
        self._neue_sets_suchen(passende, adapter.name, pokemon_liste="pokemon" in kategorie.link.lower())
        self._verarbeite(passende, shop=adapter.name, produkt=None,
                         schluessel=f"kategorie:{kategorie.link}", ueberschrift=kategorie.name, link=kategorie.link)

    # --- Deal-Feeds (mydealz) --------------------------------------------------------------

    def _pruefe_feed(self, feed: Kategorie) -> None:
        seite = self._hole(feed.link)
        if seite is None or seite.text is None:
            if seite is not None:
                log.warning("Feed %s: %s", feed.name, seite.problem)
            return
        try:
            deals = lies_rss(seite.text)
        except FeedFehler as fehler:
            log.warning("Feed %s: %s", feed.name, fehler)
            return
        passende = [d for d in deals if self._passt_filter(d.titel)]
        log.info("Feed %s: %d Deals, %d passen zum Filter", feed.name, len(deals), len(passende))

        schluessel = f"feed:{feed.link}"
        if self.speicher.meta(schluessel) is None:
            # Beim ersten Mal: alles als bekannt merken und nur eine Übersicht schicken
            zeilen = [f"{len(passende)} aktuelle Deals passen zu deinem Filter. Ab jetzt meldet der Bot "
                      "neue Deals, sobald sie gepostet werden."]
            for deal in passende[:MAX_ZEILEN_UEBERSICHT]:
                zeilen.append(f"• {als_link(deal.titel, deal.link)} – {deal.haendler or '?'}"
                              + (f", {euro(deal.preis)}" if deal.preis else ""))
            self._melde(Kasten(titel=f"📋 Neu überwacht: {feed.name}", text="\n".join(zeilen),
                               link=feed.link, farbe=FARBE_INFO),
                        *[partial(self.speicher.setze_meta, f"deal:{deal.guid}", "1") for deal in deals],
                        partial(self.speicher.setze_meta, schluessel, self.jetzt.isoformat()))
            return

        neue = [d for d in passende if self.speicher.meta(f"deal:{d.guid}") is None]
        gemeldet: set[str] = set()
        for deal in neue[:MAX_DEALS_EINZELN]:
            regeln = self._regeln_fuer(deal.titel)
            if regeln.max_preis is not None and deal.preis is not None and deal.preis > regeln.max_preis:
                log.info("Deal über Maximalpreis, kein Ping: %s", deal.titel)
            else:
                self._melde(_deal_kasten(deal, feed.name, regeln.chase_preis),
                            partial(self.speicher.setze_meta, f"deal:{deal.guid}", "1"))
                gemeldet.add(deal.guid)
        if len(neue) > MAX_DEALS_EINZELN:
            rest = neue[MAX_DEALS_EINZELN:]
            self._melde(Kasten(
                titel=f"📰 {len(rest)} weitere neue Deals: {feed.name}",
                text="\n".join(f"• {als_link(d.titel, d.link)}" for d in rest[:MAX_ZEILEN_UEBERSICHT]),
                link=feed.link, farbe=FARBE_INFO, art="kaufbar"),
                *[partial(self.speicher.setze_meta, f"deal:{d.guid}", "1") for d in rest])
            gemeldet.update(d.guid for d in rest)
        for deal in deals:  # auch unpassende merken, damit sie nie wieder geprüft werden
            if deal.guid not in gemeldet and self.speicher.meta(f"deal:{deal.guid}") is None:
                self.bestaetigungen.append(partial(self.speicher.setze_meta, f"deal:{deal.guid}", "1"))

    def _regeln_fuer(self, titel: str | None, produkt: Produkt | None = None) -> Regeln:
        """Regeln für genau dieses Produkt: Maximalpreis der Produktart im Set (z. B. „Dunkelnacht – Display“)
        > Maximalpreis des ganzen Sets > Standard-Regeln. Das Set wird notfalls am Namen erkannt."""
        return regeln_fuer(titel, self.e.watchlist, self.e.standard_regeln, produkt)

    # --- Gemeinsam für Suche und Kategorien ---------------------------------------------

    def _nur_passende(self, eintraege: list[ListenEintrag]) -> list[ListenEintrag]:
        """Filter anwenden, UNBEKANNT und schon (woanders) geprüfte Produkte weglassen."""
        return [e for e in eintraege
                if self._passt_filter(e.ergebnis.titel)
                and e.url not in self._watchlist_links
                and e.ergebnis.status != Status.UNBEKANNT]

    def _verarbeite(self, passende: list[ListenEintrag], shop: str, produkt: Produkt | None, schluessel: str,
                    ueberschrift: str, link: str | None) -> None:
        # Steht ein Produkt in mehreren Listen (z. B. Suche UND Kategorie), zählt nur das erste Vorkommen
        neu_in_diesem_lauf = [e for e in passende if e.url not in self._gesehen]
        self._gesehen.update(e.url for e in neu_in_diesem_lauf)
        for eintrag in neu_in_diesem_lauf:
            self._beobachtet[eintrag.url] = (shop, eintrag.ergebnis.titel, eintrag.ergebnis)

        if self.speicher.meta(schluessel) is None:
            self._erster_blick(neu_in_diesem_lauf, shop, produkt, schluessel, ueberschrift, link)
            return

        unbekannt = [e for e in neu_in_diesem_lauf if self.speicher.stand(e.url) is None]
        if unbekannt and self._filter_geaendert:
            # Filter wurde geändert: Diese Produkte sind nicht neu im Shop, nur neu für den Bot
            for eintrag in unbekannt:
                e = eintrag.ergebnis
                self._filter_merken.append(partial(self.speicher.setze_stand, eintrag.url, shop, e.titel, e.status,
                                                   e.preis, self.jetzt))
                self._durch_filter.append((eintrag, produkt))
            neu_in_diesem_lauf = [e for e in neu_in_diesem_lauf if e not in unbekannt]
        # Sicherung gegen eine Flut: Tauchen auf einmal viele unbekannte Produkte auf, hat meist
        # der Shop seine Liste umgestellt. Dann lieber EINE Sammelnachricht statt vieler Pings.
        elif len(unbekannt) > MAX_NEU_EINZELN:
            self._sammelnachricht(unbekannt, shop, produkt, ueberschrift, link)
            neu_in_diesem_lauf = [e for e in neu_in_diesem_lauf if e not in unbekannt]

        for eintrag in neu_in_diesem_lauf:
            e = eintrag.ergebnis
            alt = self.speicher.stand(eintrag.url)
            if alt is None or alt != (e.status, e.preis):
                # Verlauf für Listen-Produkte nur bei Änderungen speichern (spart Platz)
                self.speicher.speichere_check(eintrag.url, shop, e.titel, e, self.jetzt)
            self._vergleiche(eintrag.url, shop, e.titel or "Unbekanntes Produkt", e,
                             self._regeln_fuer(e.titel, produkt), aus_kategorie=True)

    def _preisvergleich(self) -> None:
        """Gibt es dasselbe Produkt (Set + Art + Sprache) gerade auch in einem anderen Shop? Dann steht es
        im Ping dabei. Wird erst am Ende gemacht, damit auch Shops aus demselben Lauf mitzählen."""
        if not self._pings:
            return
        angebote: dict[str, tuple[str, str | None, Status, float | None]] = {}
        # Ältere Stände (in den letzten 24 Stunden gesehen) aus der Datenbank …
        for zeile in self.speicher.verfuegbare(list(VERGLEICH_STATUS), gesehen_seit=self.jetzt - timedelta(hours=24)):
            angebote[zeile["url"]] = (zeile["shop"], zeile["produkt"], Status(zeile["status"]), zeile["preis"])
        # … überschrieben von dem, was dieser Lauf gerade gesehen hat
        for url, (shop, titel, ergebnis) in self._beobachtet.items():
            angebote[url] = (shop, titel, ergebnis.status, ergebnis.preis)

        for kasten, url, titel in self._pings:
            schluessel = vergleichs_schluessel(titel, self.e.watchlist)
            if schluessel is None:
                continue
            andere = [(shop, u, preis) for u, (shop, t, status, preis) in angebote.items()
                      if u != url and status in VERGLEICH_STATUS
                      and vergleichs_schluessel(t, self.e.watchlist) == schluessel]
            if not andere:
                continue
            andere.sort(key=lambda a: (a[2] is None, a[2] or 0))
            eigener = angebote.get(url, (None, None, None, None))[3]
            teile = []
            for shop, u, preis in andere[:3]:
                guenstiger = " 💡 günstiger" if preis is not None and eigener is not None and preis < eigener else ""
                teile.append(f"[{shop}]({u}) {euro(preis) if preis is not None else 'Preis im Shop'}{guenstiger}")
            kasten.text += "\n🔎 Auch verfügbar: " + " · ".join(teile)

    def _neue_sets_suchen(self, eintraege: list[ListenEintrag], shop: str, pokemon_liste: bool) -> None:
        """Vorbestellungen/Vorverkauf von Sets, die nicht auf der Watchlist stehen, merken.

        pokemon_liste: Die Liste enthält nur Pokémon (z. B. …/Pokemon-Karten/…). Sonst muss „Pokémon“ im
        Namen stehen – Listen wie „Neu eingetroffen“ enthalten auch andere Kartenspiele."""
        for eintrag in eintraege:
            titel = eintrag.ergebnis.titel
            if not pokemon_liste and not re.search(r"pok[eé]mon", titel or "", re.I):
                continue
            # Nur an den Grundprodukten jedes Sets erkennen – Kollektionen & Mini-Tins tragen Pokémon-Namen im Titel
            if produktart(titel) not in ("Display", "Top-Trainer-Box", "Booster Bundle"):
                continue
            vorverkauf = eintrag.ergebnis.status in (Status.VORBESTELLBAR, Status.BALD) or "vorverkauf" in (
                titel or "").lower()
            if not vorverkauf or set_fuer(titel, self.e.watchlist) is not None:
                continue
            name = set_name_aus_titel(titel)
            if name:
                self._neue_sets.setdefault(name, []).append((shop, titel, eintrag.url))

    def _neue_sets_melden(self) -> None:
        """Jedes neue Set wird nur EINMAL gemeldet – mit Anleitung zum Hinzufügen."""
        neu = {name: beispiele for name, beispiele in self._neue_sets.items()
               if self.speicher.meta(f"set_vorschlag:{vereinfacht(name)}") is None}
        if not neu:
            return
        zeilen = ["Diese Sets sind im Vorverkauf, stehen aber nicht auf deiner Watchlist:"]
        merken = []
        for name, beispiele in list(neu.items())[:MAX_ZEILEN_UEBERSICHT]:
            shop, titel, url = beispiele[0]
            zeilen.append(f"• **{name}** – z. B. {als_link(titel, url)} bei {shop}"
                          + (f" (+{len(beispiele) - 1} weitere)" if len(beispiele) > 1 else ""))
            merken.append(partial(self.speicher.setze_meta, f"set_vorschlag:{vereinfacht(name)}",
                                  self.jetzt.isoformat()))
        zeilen.append("Beobachten? Actions → Preis-Bot → Run workflow → **set-hinzufuegen**, bei „name“ den "
                      "Set-Namen eintragen (englischen/japanischen Namen bei „suchbegriffe“). "
                      "Jedes Set wird nur einmal vorgeschlagen.")
        namen = ", ".join(list(neu)[:3]) + (" …" if len(neu) > 3 else "")
        self._melde(Kasten(titel=f"🆕 Neue Sets entdeckt: {namen}",
                           text="\n".join(zeilen), farbe=FARBE_INFO), *merken)

    def _filter_uebersicht(self) -> None:
        """Nach einer Filter-Änderung: EINE Nachricht mit allem, was jetzt zusätzlich überwacht wird."""
        if not self._filter_geaendert:
            return
        filter_merken = partial(self.speicher.setze_meta, "filter", self._filter_stempel)
        if not self._durch_filter:
            self.bestaetigungen.append(filter_merken)
            return
        verfuegbar = [(eintrag, produkt) for eintrag, produkt in self._durch_filter
                      if self._wuerde_pingen(eintrag, produkt)]
        log.info("Filter geändert: %d Produkte neu überwacht, davon %d verfügbar", len(self._durch_filter),
                 len(verfuegbar))
        zeilen = [f"Durch deine Filter-Änderung überwacht der Bot jetzt {len(self._durch_filter)} weitere Produkte, "
                  f"davon {len(verfuegbar)} gerade verfügbar. Die waren schon vorher im Shop – deshalb keine "
                  "Einzel-Pings, nur diese Übersicht:"]
        for eintrag, _ in verfuegbar[:MAX_ZEILEN_UEBERSICHT]:
            e = eintrag.ergebnis
            termin = f" · ab {e.liefertermin}" if e.liefertermin else ""
            zeilen.append(f"{EMOJI[e.status]} {als_link(e.titel, eintrag.url)} – {preis_text(e)}{termin}")
        if len(verfuegbar) > MAX_ZEILEN_UEBERSICHT:
            zeilen.append(f"… und {len(verfuegbar) - MAX_ZEILEN_UEBERSICHT} weitere")
        zeilen.append("Ab jetzt bekommst du für diese Produkte ganz normal Pings bei Änderungen.")
        self._melde(Kasten(titel=f"🔧 Filter geändert – {len(self._durch_filter)} Produkte neu überwacht",
                           text="\n".join(zeilen), farbe=FARBE_INFO), filter_merken, *self._filter_merken)

    def _sammelnachricht(self, unbekannt: list[ListenEintrag], shop: str, produkt: Produkt | None, ueberschrift: str,
                         link: str | None) -> None:
        verfuegbar = [e for e in unbekannt if self._wuerde_pingen(e, produkt)]
        merken = [partial(self.speicher.setze_stand, eintrag.url, shop, eintrag.ergebnis.titel, eintrag.ergebnis.status,
                          eintrag.ergebnis.preis, self.jetzt) for eintrag in unbekannt]
        log.info("%s: %d unbekannte Produkte auf einmal – Sammelnachricht statt Einzel-Pings",
                 ueberschrift, len(unbekannt))
        if not verfuegbar:
            self.bestaetigungen.extend(merken)
            return
        zeilen = [f"{len(unbekannt)} Produkte tauchen neu in der Liste auf, davon {len(verfuegbar)} verfügbar. "
                  "Vermutlich hat der Shop die Liste umgestellt – deshalb nur diese eine Nachricht:"]
        for eintrag in verfuegbar[:MAX_ZEILEN_UEBERSICHT]:
            e = eintrag.ergebnis
            zeilen.append(f"{EMOJI[e.status]} {als_link(e.titel, eintrag.url)} – {preis_text(e)}")
        if len(verfuegbar) > MAX_ZEILEN_UEBERSICHT:
            zeilen.append(f"… und {len(verfuegbar) - MAX_ZEILEN_UEBERSICHT} weitere")
        self._melde(Kasten(titel=f"🗂️ Viele neue Einträge: {ueberschrift}", text="\n".join(zeilen),
                           link=link, farbe=FARBE_INFO), *merken)

    def _erster_blick(self, passende: list[ListenEintrag], shop: str, produkt: Produkt | None, schluessel: str,
                      ueberschrift: str, link: str | None) -> None:
        """Beim ersten Mal nicht jedes Produkt einzeln melden – nur eine Übersicht schicken.

        Produkte, die der Bot schon kennt (z. B. aus einer anderen Liste), werden trotzdem ganz normal
        verglichen – sonst ginge ein „wieder verfügbar“ verloren, wenn du ein Set neu hinzufügst.
        """
        for eintrag in passende:
            e = eintrag.ergebnis
            if self.speicher.stand(eintrag.url) is None:
                self.speicher.setze_stand(eintrag.url, shop, e.titel, e.status, e.preis, self.jetzt)
                self.speicher.speichere_check(eintrag.url, shop, e.titel, e, self.jetzt)
            # Bekannte Produkte normal vergleichen; bei neuen meldet das nur einen Chasepreis extra
            self._vergleiche(eintrag.url, shop, e.titel or "Unbekanntes Produkt", e,
                             self._regeln_fuer(e.titel, produkt), aus_kategorie=True)
        interessant = [e for e in passende if self._wuerde_pingen(e, produkt)]
        if passende:
            zeilen = [f"{len(passende)} passende Produkte, davon {len(interessant)} gerade verfügbar."]
        else:
            zeilen = ["Gerade keine passenden Produkte. Du bekommst Bescheid, sobald welche auftauchen."]
        for eintrag in interessant[:MAX_ZEILEN_UEBERSICHT]:
            e = eintrag.ergebnis
            termin = f" · ab {e.liefertermin}" if e.liefertermin else ""
            zeilen.append(f"{EMOJI[e.status]} {als_link(e.titel, eintrag.url)} – {preis_text(e)}{termin}")
        if len(interessant) > MAX_ZEILEN_UEBERSICHT:
            zeilen.append(f"… und {len(interessant) - MAX_ZEILEN_UEBERSICHT} weitere")
        zeilen.append("Ab jetzt bekommst du hier nur noch Neuigkeiten.")
        self._melde(Kasten(titel=f"📋 Neu überwacht: {ueberschrift}", text="\n".join(zeilen),
                           link=link, farbe=FARBE_INFO),
                    partial(self.speicher.setze_meta, schluessel, self.jetzt.isoformat()))

    def _wuerde_pingen(self, eintrag: ListenEintrag, produkt: Produkt | None) -> bool:
        """Gleiche Regeln wie beim Ping (Status, Maximalpreis des Produkts, Vertrauensliste …)."""
        vertraut = domain_von(eintrag.url) in self.e.vertrauenswuerdige_shops
        regeln = self._regeln_fuer(eintrag.ergebnis.titel, produkt)
        return ping_grund(None, eintrag.ergebnis, regeln, vertraut) is not None

    def _passt_filter(self, titel: str | None) -> bool:
        filter_ = self.e.kategorie_filter
        if filter_.nur_mit and not any(enthaelt_wort(titel, w) for w in filter_.nur_mit):
            return False
        return not any(enthaelt_wort(titel, w) for w in filter_.ohne)

    # --- Vergleichen und Melden -------------------------------------------------------

    def _vergleiche(self, url: str, shop: str, name: str, ergebnis: CheckErgebnis, regeln: Regeln,
                    aus_kategorie: bool, titel: str | None = None) -> None:
        if ergebnis.status == Status.UNBEKANNT:
            return  # letzten bekannten Stand behalten
        alt = self.speicher.stand(url)
        vertraut = domain_von(url) in self.e.vertrauenswuerdige_shops
        grund = ping_grund(alt, ergebnis, regeln, vertraut)
        merken = [partial(self.speicher.setze_stand, url, shop, name, ergebnis.status, ergebnis.preis, self.jetzt)]

        # Chasepreis: einmal melden, solange das Produkt darunter bleibt – auch wenn sich sonst nichts
        # geändert hat (z. B. weil du den Chasepreis gerade erst eingetragen hast)
        chase_schluessel = f"chase:{url}"
        chase_jetzt = ist_chase(ergebnis, regeln) and ping_grund(None, ergebnis, regeln, vertraut) is not None
        if chase_jetzt:
            if grund is None and self.speicher.meta(chase_schluessel) is None:
                grund = "chasepreis"
            merken.append(partial(self.speicher.setze_meta, chase_schluessel, str(ergebnis.preis)))
        elif self.speicher.meta(chase_schluessel) is not None:
            self.speicher.setze_meta(chase_schluessel, None)  # wieder teurer/weg → nächstes Mal neu melden

        if grund:
            kasten = ping_kasten(name, shop, url, ergebnis, alt, grund, vertraut, aus_kategorie,
                                 max_preis=regeln.max_preis, chase_preis=regeln.chase_preis)
            self._melde(kasten, *merken)
            self._pings.append((kasten, url, titel or name))
        else:
            for m in merken:
                m()

    def _melde(self, kasten: Kasten, *merken) -> None:
        """Kasten für Discord vormerken. „merken“ läuft erst, wenn GENAU dieser Kasten verschickt ist."""
        self.kaesten.append(kasten)
        self._zu_kasten[id(kasten)] = list(merken)

    def _einmal_melden(self, schluessel: str, kasten: Kasten) -> None:
        """Hinweise, die nur ein einziges Mal kommen sollen (z. B. „Link kaputt“)."""
        if schluessel not in self._hinweise and self.speicher.meta(f"hinweis:{schluessel}") is None:
            self._hinweise.add(schluessel)
            self._melde(kasten, partial(self.speicher.setze_meta, f"hinweis:{schluessel}", self.jetzt.isoformat()))

    def _kein_adapter(self, url: str) -> None:
        domain = domain_von(url)
        grund = NICHT_ERLAUBT.get(domain)
        if grund:
            log.warning("%s wird nicht abgefragt: %s", domain, grund)
            self._einmal_melden(f"nicht_erlaubt:{domain}", Kasten(
                titel=f"🚫 {domain} wird nicht automatisch geprüft", text=grund, farbe=FARBE_WARNUNG))
        else:
            log.warning("Für %s gibt es noch keinen Adapter – Link wird übersprungen: %s", domain, url)
            self._einmal_melden(f"kein_adapter:{domain}", Kasten(
                titel=f"ℹ️ {domain} wird noch nicht unterstützt",
                text="Für diesen Shop gibt es noch keinen Adapter. Sag Bescheid, dann baue ich einen.",
                farbe=FARBE_INFO))

    # --- Abrufen ------------------------------------------------------------------------

    def _hole(self, url: str) -> Seite | None:
        """Holt eine Seite – oder None, wenn der Shop gerade nicht abgefragt werden soll."""
        adapter = adapter_fuer(url)
        abruf = adapter.abruf_url(url) if adapter else url  # z. B. Games Island: crawlme-Adresse
        domain = domain_von(abruf)
        if domain in self._gesperrt or not self._shop_ist_frei(domain):
            return None
        seite = self.abrufer.hole(abruf)
        shop = adapter.name if adapter else domain
        if seite.gesperrt:
            # Nicht weiter anfragen und NICHT umgehen – nur einmal Bescheid geben
            self._gesperrt.add(domain)
            log.warning("%s: %s", shop, seite.problem)
            if self.speicher.blockade(domain) is None:
                self._melde(Kasten(
                    titel=f"⚠️ {shop} blockt den Bot",
                    text=f"{seite.problem}.\nDer Bot umgeht das nicht. Der Status dort ist vorerst UNBEKANNT.\n"
                         "Du bekommst Bescheid, sobald es wieder klappt.",
                    farbe=FARBE_WARNUNG), partial(self.speicher.setze_blockade, domain, seite.problem))
        elif (seite.text is not None and domain not in self._wieder_frei
              and self.speicher.blockade(domain) is not None):
            self._wieder_frei.add(domain)
            self._melde(Kasten(titel=f"✅ {shop} ist wieder erreichbar",
                               text="Der Bot prüft dort wieder ganz normal.", farbe=0x2ECC71),
                        partial(self.speicher.setze_blockade, domain, None))
        return seite

    def _shop_ist_frei(self, domain: str) -> bool:
        """Höflichkeitsregel: jeden Shop höchstens alle X Minuten (siehe config.yaml)."""
        if domain not in self._shop_frei:
            letzter = self.speicher.letzter_abruf(domain)
            abstand = timedelta(minutes=max(self.e.allgemein.min_minuten_pro_shop - TOLERANZ_MINUTEN, 1))
            frei = letzter is None or self.jetzt - letzter >= abstand
            if frei:
                self.speicher.setze_abruf(domain, self.jetzt)
            else:
                log.info("%s wurde vor Kurzem erst abgefragt – diesmal ausgelassen.", domain)
            self._shop_frei[domain] = frei
        return self._shop_frei[domain]

    # --- Senden ---------------------------------------------------------------------------

    def _senden(self) -> int:
        self.speicher.setze_meta("letzter_lauf", self.jetzt.isoformat())
        jetzt, spaeter = self._nach_ruhezeit(self.kaesten)
        if spaeter:
            log.info("Ruhezeit %s: %d Nachricht(en) kommen erst danach:", self.e.standard_regeln.ruhezeit, len(spaeter))
            for kasten in spaeter:
                log.info("  ⏸ %s", kasten.titel)
        if not jetzt:
            for bestaetigen in self.bestaetigungen:  # z. B. still gemerkte Produkte
                bestaetigen()
            if not spaeter:
                log.info("Keine Neuigkeiten.")
            return 0
        if self.melder is None:
            log.warning("%d Neuigkeit(en), aber Discord ist noch nicht eingerichtet:", len(jetzt))
            for kasten in jetzt:
                log.warning("  • %s", kasten.titel)
            return 0
        # Kaufbares, Einladungen und Infos kommen als getrennte Nachrichten (je eine Mitteilung)
        for text, kaesten in nach_art(jetzt):
            self.melder.sende(text=text, kaesten=kaesten)
        for bestaetigen in self.bestaetigungen + [b for k in jetzt for b in self._zu_kasten.get(id(k), [])]:
            bestaetigen()
        log.info("%d Neuigkeit(en) an Discord geschickt:", len(jetzt))
        for kasten in jetzt:
            log.info("  • %s", kasten.titel)
        return 0

    def _nach_ruhezeit(self, kaesten: list[Kasten]) -> tuple[list[Kasten], list[Kasten]]:
        """Teilt in (jetzt schicken, nach der Ruhezeit schicken).

        In der Ruhezeit kommt nur Dringendes (🛒 kaufbar, 🟡 Einladung) – oder mit
        in_ruhezeit_nur_dringend: false gar nichts. Alles andere kommt beim ersten Lauf danach.
        """
        if not in_ruhezeit(self.e.standard_regeln.ruhezeit, self.jetzt, self.e.allgemein.zeitzone):
            return kaesten, []
        if not self.e.standard_regeln.in_ruhezeit_nur_dringend:
            return [], kaesten
        dringend = [k for k in kaesten if k.art in DRINGEND]
        return dringend, [k for k in kaesten if k.art not in DRINGEND]

def in_ruhezeit(ruhezeit: str | None, jetzt: datetime, zeitzone: str) -> bool:
    """'03:00-06:00' → True zwischen 3 und 6 Uhr (Ortszeit). Geht auch über Mitternacht, z. B. '22:00-06:00'."""
    if not ruhezeit:
        return False
    von, bis = ruhezeit.split("-")
    uhrzeit = jetzt.astimezone(ZoneInfo(zeitzone)).strftime("%H:%M")
    if von <= bis:
        return von <= uhrzeit < bis
    return uhrzeit >= von or uhrzeit < bis


def _stempel(*listen) -> str:
    """Kurzer „Fingerabdruck“ des Filters, um Änderungen zu erkennen."""
    daten = json.dumps([sorted(w.casefold() for w in liste) for liste in listen], ensure_ascii=False)
    return hashlib.sha1(daten.encode("utf-8")).hexdigest()[:12]


def _deal_kasten(deal: Deal, quelle: str, chase_preis: float | None = None) -> Kasten:
    zeilen = [f"**{deal.haendler or 'Händler unbekannt'}** · " + (euro(deal.preis) if deal.preis else "Preis im Deal")]
    if chase_preis is not None and deal.preis is not None and deal.preis <= chase_preis:
        zeilen.insert(0, f"🚨 **{euro(deal.preis)} – unter deinem Chasepreis von {euro(chase_preis)}!** 🚨")
        if deal.mit_einladung:
            zeilen.append("🟡 Nur auf Einladung (z. B. bei Amazon „Einladung anfordern“)")
        zeilen.append(f"Gefunden über {quelle} – tipp auf die Überschrift, dort steht der Link zum Shop.")
        return Kasten(titel=f"🚨 CHASEPREIS-DEAL – {deal.titel}"[:256], text="\n".join(zeilen), link=deal.link,
                      farbe=FARBE_CHASE, art="chase")
    if deal.mit_einladung:
        zeilen.append("🟡 Nur auf Einladung (z. B. bei Amazon „Einladung anfordern“)")
    zeilen.append(f"Gefunden über {quelle} – tipp auf die Überschrift, dort steht der Link zum Shop.")
    if deal.mit_einladung:
        return Kasten(titel=f"🟡 EINLADUNG – {deal.titel}"[:256], text="\n".join(zeilen), link=deal.link,
                      farbe=0xF1C40F, art="einladung")
    return Kasten(titel=f"📰 DEAL – {deal.titel}"[:256], text="\n".join(zeilen), link=deal.link,
                  farbe=0x2ECC71, art="kaufbar")
