"""Der normale Lauf (alle 15 Minuten): Produkte und Kategorien prüfen, Änderungen melden.

Ablauf:
1. Watchlist: feste Produkt-Links prüfen und Suchbegriffe (z. B. Set-Namen) in allen
   unterstützten Shops suchen – jedes passende Produkt wird beobachtet
2. Jede überwachte Kategorie nach neuen Produkten und Vorbestellungen durchsuchen
3. Alle Neuigkeiten in EINER Discord-Nachricht schicken

Wichtig: Der neue Stand wird erst gespeichert, wenn die Nachricht wirklich
angekommen ist. Klappt der Versand nicht, versucht es der nächste Lauf nochmal –
so geht kein Ping verloren.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from functools import partial

from bot.abruf import Abrufer, Seite
from bot.adapter import ADAPTER, NICHT_ERLAUBT, adapter_fuer
from bot.adapter.basis import CheckErgebnis, ListenEintrag, domain_von
from bot.discord import DiscordWebhook, Kasten
from bot.einstellungen import Einstellungen, Kategorie, Produkt, Regeln
from bot.pings import EMOJI, FARBE_INFO, FARBE_WARNUNG, euro, ping_grund, ping_kasten, zusammenfassung
from bot.speicher import Speicher
from bot.status import Status

log = logging.getLogger("bot")


def enthaelt_wort(text: str | None, wort: str) -> bool:
    """True, wenn 'wort' als eigenes Wort im Text steht (Groß-/Kleinschreibung egal)."""
    return re.search(rf"(?<!\w){re.escape(wort)}(?!\w)", text or "", re.IGNORECASE) is not None

MAX_ZEILEN_UEBERSICHT = 10
MAX_SUCHSEITEN = 3   # höchstens so viele Ergebnisseiten pro Suchbegriff und Shop
MAX_NEU_EINZELN = 5  # mehr „neue“ Produkte auf einmal → eine Sammelnachricht statt vieler Pings
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
        self._shop_frei: dict[str, bool] = {}
        self._gesperrt: set[str] = set()
        self._wieder_frei: set[str] = set()
        self._hinweise: set[str] = set()
        self._gesehen: set[str] = set()
        self._watchlist_links = {link for p in self.e.watchlist for link in p.links}

    def starten(self) -> int:
        log.info("Normaler Lauf: %d Watchlist-Eintrag/-Einträge, %d Kategorie(n)",
                 len(self.e.watchlist), len(self.e.kategorien))
        for produkt in self.e.watchlist:
            for link in produkt.links:
                self._pruefe_produkt(produkt, link)
            if produkt.suche:
                self._pruefe_suche(produkt)
        for kategorie in self.e.kategorien:
            self._pruefe_kategorie(kategorie)
        return self._senden()

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
        self._vergleiche(url, adapter.name, produkt.name, ergebnis, produkt.regeln, aus_kategorie=False)

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
            self._verarbeite(passende, shop=adapter.name, regeln=produkt.regeln,
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
        self._verarbeite(passende, shop=adapter.name, regeln=self.e.standard_regeln,
                         schluessel=f"kategorie:{kategorie.link}", ueberschrift=kategorie.name, link=kategorie.link)

    # --- Gemeinsam für Suche und Kategorien ---------------------------------------------

    def _nur_passende(self, eintraege: list[ListenEintrag]) -> list[ListenEintrag]:
        """Filter anwenden, UNBEKANNT und schon (woanders) geprüfte Produkte weglassen."""
        return [e for e in eintraege
                if self._passt_filter(e.ergebnis.titel)
                and e.url not in self._watchlist_links
                and e.ergebnis.status != Status.UNBEKANNT]

    def _verarbeite(self, passende: list[ListenEintrag], shop: str, regeln: Regeln, schluessel: str,
                    ueberschrift: str, link: str | None) -> None:
        # Steht ein Produkt in mehreren Listen (z. B. Suche UND Kategorie), zählt nur das erste Vorkommen
        neu_in_diesem_lauf = [e for e in passende if e.url not in self._gesehen]
        self._gesehen.update(e.url for e in neu_in_diesem_lauf)

        if self.speicher.meta(schluessel) is None:
            self._erster_blick(neu_in_diesem_lauf, shop, regeln, schluessel, ueberschrift, link)
            return

        # Sicherung gegen eine Flut: Tauchen auf einmal viele unbekannte Produkte auf, hat meist
        # der Shop seine Liste umgestellt. Dann lieber EINE Sammelnachricht statt vieler Pings.
        unbekannt = [e for e in neu_in_diesem_lauf if self.speicher.stand(e.url) is None]
        if len(unbekannt) > MAX_NEU_EINZELN:
            self._sammelnachricht(unbekannt, shop, regeln, ueberschrift, link)
            neu_in_diesem_lauf = [e for e in neu_in_diesem_lauf if e not in unbekannt]

        for eintrag in neu_in_diesem_lauf:
            e = eintrag.ergebnis
            alt = self.speicher.stand(eintrag.url)
            if alt is None or alt != (e.status, e.preis):
                # Verlauf für Listen-Produkte nur bei Änderungen speichern (spart Platz)
                self.speicher.speichere_check(eintrag.url, shop, e.titel, e, self.jetzt)
            self._vergleiche(eintrag.url, shop, e.titel or "Unbekanntes Produkt", e, regeln, aus_kategorie=True)

    def _sammelnachricht(self, unbekannt: list[ListenEintrag], shop: str, regeln: Regeln, ueberschrift: str,
                         link: str | None) -> None:
        verfuegbar = [e for e in unbekannt if e.ergebnis.status in regeln.ping_bei_status]
        for eintrag in unbekannt:
            e = eintrag.ergebnis
            self.bestaetigungen.append(partial(self.speicher.setze_stand, eintrag.url, shop, e.titel, e.status,
                                               e.preis, self.jetzt))
        log.info("%s: %d unbekannte Produkte auf einmal – Sammelnachricht statt Einzel-Pings",
                 ueberschrift, len(unbekannt))
        if not verfuegbar:
            return
        zeilen = [f"{len(unbekannt)} Produkte tauchen neu in der Liste auf, davon {len(verfuegbar)} verfügbar. "
                  "Vermutlich hat der Shop die Liste umgestellt – deshalb nur diese eine Nachricht:"]
        for eintrag in verfuegbar[:MAX_ZEILEN_UEBERSICHT]:
            e = eintrag.ergebnis
            zeilen.append(f"{EMOJI[e.status]} [{e.titel}]({eintrag.url}) – {euro(e.preis)}")
        if len(verfuegbar) > MAX_ZEILEN_UEBERSICHT:
            zeilen.append(f"… und {len(verfuegbar) - MAX_ZEILEN_UEBERSICHT} weitere")
        self.kaesten.append(Kasten(titel=f"🗂️ Viele neue Einträge: {ueberschrift}", text="\n".join(zeilen),
                                   link=link, farbe=FARBE_INFO))

    def _erster_blick(self, passende: list[ListenEintrag], shop: str, regeln: Regeln, schluessel: str,
                      ueberschrift: str, link: str | None) -> None:
        """Beim ersten Mal nicht jedes Produkt einzeln melden – nur eine Übersicht schicken."""
        for eintrag in passende:
            if self.speicher.stand(eintrag.url) is None:
                self.speicher.setze_stand(eintrag.url, shop, eintrag.ergebnis.titel, eintrag.ergebnis.status,
                                          eintrag.ergebnis.preis, self.jetzt)
        interessant = [e for e in passende if e.ergebnis.status in regeln.ping_bei_status]
        if passende:
            zeilen = [f"{len(passende)} passende Produkte, davon {len(interessant)} gerade verfügbar."]
        else:
            zeilen = ["Gerade keine passenden Produkte. Du bekommst Bescheid, sobald welche auftauchen."]
        for eintrag in interessant[:MAX_ZEILEN_UEBERSICHT]:
            e = eintrag.ergebnis
            termin = f" · ab {e.liefertermin}" if e.liefertermin else ""
            zeilen.append(f"{EMOJI[e.status]} [{e.titel}]({eintrag.url}) – {euro(e.preis)}{termin}")
        if len(interessant) > MAX_ZEILEN_UEBERSICHT:
            zeilen.append(f"… und {len(interessant) - MAX_ZEILEN_UEBERSICHT} weitere")
        zeilen.append("Ab jetzt bekommst du hier nur noch Neuigkeiten.")
        self.kaesten.append(Kasten(titel=f"📋 Neu überwacht: {ueberschrift}", text="\n".join(zeilen),
                                   link=link, farbe=FARBE_INFO))
        self.bestaetigungen.append(partial(self.speicher.setze_meta, schluessel, self.jetzt.isoformat()))

    def _passt_filter(self, titel: str | None) -> bool:
        filter_ = self.e.kategorie_filter
        if filter_.nur_mit and not any(enthaelt_wort(titel, w) for w in filter_.nur_mit):
            return False
        return not any(enthaelt_wort(titel, w) for w in filter_.ohne)

    # --- Vergleichen und Melden -------------------------------------------------------

    def _vergleiche(self, url: str, shop: str, name: str, ergebnis: CheckErgebnis, regeln: Regeln,
                    aus_kategorie: bool) -> None:
        if ergebnis.status == Status.UNBEKANNT:
            return  # letzten bekannten Stand behalten
        alt = self.speicher.stand(url)
        vertraut = domain_von(url) in self.e.vertrauenswuerdige_shops
        grund = ping_grund(alt, ergebnis, regeln, vertraut)
        merken = partial(self.speicher.setze_stand, url, shop, name, ergebnis.status, ergebnis.preis, self.jetzt)
        if grund:
            self.kaesten.append(ping_kasten(name, shop, url, ergebnis, alt, grund, vertraut, aus_kategorie))
            self.bestaetigungen.append(merken)
        else:
            merken()

    def _einmal_melden(self, schluessel: str, kasten: Kasten) -> None:
        """Hinweise, die nur ein einziges Mal kommen sollen (z. B. „Link kaputt“)."""
        if schluessel not in self._hinweise and self.speicher.meta(f"hinweis:{schluessel}") is None:
            self._hinweise.add(schluessel)
            self.kaesten.append(kasten)
            self.bestaetigungen.append(partial(self.speicher.setze_meta, f"hinweis:{schluessel}",
                                               self.jetzt.isoformat()))

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
        domain = domain_von(url)
        if domain in self._gesperrt or not self._shop_ist_frei(domain):
            return None
        seite = self.abrufer.hole(url)
        adapter = adapter_fuer(url)
        shop = adapter.name if adapter else domain
        if seite.gesperrt:
            # Nicht weiter anfragen und NICHT umgehen – nur einmal Bescheid geben
            self._gesperrt.add(domain)
            log.warning("%s: %s", shop, seite.problem)
            if self.speicher.blockade(domain) is None:
                self.kaesten.append(Kasten(
                    titel=f"⚠️ {shop} blockt den Bot",
                    text=f"{seite.problem}.\nDer Bot umgeht das nicht. Der Status dort ist vorerst UNBEKANNT.\n"
                         "Du bekommst Bescheid, sobald es wieder klappt.",
                    farbe=FARBE_WARNUNG))
                self.bestaetigungen.append(partial(self.speicher.setze_blockade, domain, seite.problem))
        elif (seite.text is not None and domain not in self._wieder_frei
              and self.speicher.blockade(domain) is not None):
            self._wieder_frei.add(domain)
            self.kaesten.append(Kasten(titel=f"✅ {shop} ist wieder erreichbar",
                                       text="Der Bot prüft dort wieder ganz normal.", farbe=0x2ECC71))
            self.bestaetigungen.append(partial(self.speicher.setze_blockade, domain, None))
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
        if not self.kaesten:
            for bestaetigen in self.bestaetigungen:  # z. B. still gemerkte Produkte
                bestaetigen()
            log.info("Keine Neuigkeiten.")
            return 0
        if self.melder is None:
            log.warning("%d Neuigkeit(en), aber Discord ist noch nicht eingerichtet:", len(self.kaesten))
            for kasten in self.kaesten:
                log.warning("  • %s", kasten.titel)
            return 0
        self.melder.sende(text=zusammenfassung(self.kaesten), kaesten=self.kaesten)
        for bestaetigen in self.bestaetigungen:
            bestaetigen()
        log.info("%d Neuigkeit(en) an Discord geschickt:", len(self.kaesten))
        for kasten in self.kaesten:
            log.info("  • %s", kasten.titel)
        return 0
