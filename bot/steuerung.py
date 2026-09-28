"""Steuerung über die GitHub-App: Actions → Preis-Bot → Run workflow.

Die Aktionen ändern bei Bedarf die config.yaml – die Kommentare darin bleiben
erhalten. Der Workflow speichert die geänderte Datei danach automatisch im Repo.
Vor dem Speichern wird die neue Datei geprüft: Ist etwas kaputt, bleibt alles beim Alten.
"""

from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from bot.einstellungen import ConfigFehler, lade_einstellungen
from bot.pings import euro
from bot.produkte import ARTEN, SPRACHEN, PreisSchluessel, art_aus_eingabe, preis_schluessel

GANZES_SET = ("", "ganzes set", "set", "alle", "alles")


class SteuerFehler(Exception):
    """Die Eingabe passt nicht (z. B. unbekanntes Set). Die Meldung erklärt, was los ist."""


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)  # so eingerückt wie unsere config.yaml
    yaml.width = 4096
    yaml.representer.add_representer(
        type(None), lambda rep, _: rep.represent_scalar("tag:yaml.org,2002:null", "null")
    )
    return yaml


def preis_aus_eingabe(text: str | None) -> float | None:
    """'180', '180,50', '180 €' → Zahl; 'aus', 'kein', '0' oder leer → None (kein Maximalpreis)."""
    sauber = (text or "").strip().lower().replace("€", "").replace("eur", "").strip()
    if sauber in ("", "aus", "kein", "keiner", "keine", "none", "null", "0"):
        return None
    try:
        preis = float(sauber.replace(".", "").replace(",", ".") if "," in sauber else sauber)
    except ValueError:
        raise SteuerFehler(f"„{text}“ ist kein Preis. Beispiele: 180 oder 179,90 – oder „aus“.") from None
    if preis <= 0:
        raise SteuerFehler("Der Maximalpreis muss größer als 0 sein – oder „aus“.")
    return round(preis, 2)


class ConfigBearbeiter:
    def __init__(self, pfad: Path | str):
        self.pfad = Path(pfad)
        self._yaml = _yaml()
        self.daten = self._yaml.load(self.pfad.read_text(encoding="utf-8"))
        if self.daten.get("watchlist") is None:
            self.daten["watchlist"] = CommentedSeq()
        if self.daten.get("allgemein") is None:
            self.daten["allgemein"] = CommentedMap()

    @property
    def watchlist(self) -> CommentedSeq:
        return self.daten["watchlist"]

    # --- Aktionen ------------------------------------------------------------------------

    def set_hinzufuegen(self, name: str, suchbegriffe: list[str]) -> dict:
        name = (name or "").strip()
        if not name:
            raise SteuerFehler("Bitte bei „name“ den Set-Namen eintragen, z. B. Dunkelnacht.")
        if self._suche_eintrag(name, genau=True) is not None:
            raise SteuerFehler(f"„{name}“ steht schon auf der Watchlist.")
        begriffe = [name] + [b for b in suchbegriffe if b.casefold() != name.casefold()]
        eintrag = CommentedMap()
        eintrag["name"] = name
        eintrag["suche"] = CommentedSeq(begriffe)
        eintrag["suche"].fa.set_block_style()
        # Ganz oben einfügen: Am Ende der Liste würde es unter den Kommentar der Kategorien rutschen
        self.watchlist.fa.set_block_style()
        self.watchlist.insert(0, eintrag)
        return eintrag

    def set_entfernen(self, name: str) -> dict:
        eintrag = self._finde(name)
        self.watchlist.remove(eintrag)
        return eintrag

    def max_preis(self, name: str, preis: float | None, art: str | None = None, sprache: str | None = None,
                  tabelle: str = "preise") -> dict:
        """Maximalpreis (tabelle="preise") oder Chasepreis (tabelle="chase") setzen.

        art=None: Maximalpreis fürs ganze Set. Sonst für eine Produktart, optional nur für eine Sprache.
        """
        eintrag = self._finde(name)
        wert = None if preis is None else (int(preis) if float(preis).is_integer() else preis)
        if art is None and (tabelle == "chase" or sprache):
            raise SteuerFehler("Bitte bei „produkt“ ein Produkt auswählen (z. B. Display) – "
                               + ("einen Chasepreis gibt es nur je Produkt, nicht fürs ganze Set."
                                  if tabelle == "chase" else "die Sprache geht nur zusammen mit einem Produkt."))
        if art is None:
            if wert is None:
                eintrag.pop("max_preis", None)
            elif "max_preis" in eintrag:
                eintrag["max_preis"] = wert
            else:
                eintrag.insert(1, "max_preis", wert)  # direkt unter den Namen
            return eintrag

        ziel = PreisSchluessel(art=art, sprache=sprache)
        gleich = [s for s in (eintrag.get(tabelle) or {}) if preis_schluessel(str(s)) == ziel]
        preise = eintrag.get(tabelle)
        if wert is None:
            for schluessel in gleich:
                del preise[schluessel]
            if preise is not None and not preise:
                del eintrag[tabelle]
            return eintrag
        if preise is None:
            preise = CommentedMap()
            # unter den Namen, den Preis fürs ganze Set und (beim Chasepreis) die Maximalpreise
            davor = 1 + sum(1 for k in ("max_preis", "preise") if k in eintrag and k != tabelle)
            eintrag.insert(davor, tabelle, preise)
        for schluessel in gleich:
            if schluessel != ziel.text:
                del preise[schluessel]  # alte Schreibweise (z. B. „ttb de“) durch die einheitliche ersetzen
        preise[ziel.text] = wert
        return eintrag

    def pause(self, an: bool) -> None:
        allgemein = self.daten["allgemein"]
        if "pausiert" in allgemein:
            allgemein["pausiert"] = an
        else:
            allgemein.insert(0, "pausiert", an)  # oben, damit es nicht unter fremde Kommentare rutscht

    # --- Speichern ------------------------------------------------------------------------

    def speichern(self) -> None:
        """Schreibt die Datei – aber nur, wenn die neue Fassung gültig ist."""
        puffer = io.StringIO()
        self._yaml.dump(self.daten, puffer)
        probe = self.pfad.with_name(self.pfad.name + ".probe")
        probe.write_text(puffer.getvalue(), encoding="utf-8")
        try:
            lade_einstellungen(probe)
        except ConfigFehler as fehler:
            raise SteuerFehler(f"Die Änderung würde config.yaml kaputt machen: {fehler}") from None
        finally:
            probe.unlink(missing_ok=True)
        self.pfad.write_text(puffer.getvalue(), encoding="utf-8")

    # --- Hilfen ---------------------------------------------------------------------------

    def _suche_eintrag(self, name: str, genau: bool = False):
        gesucht = (name or "").strip().casefold()
        if not gesucht:
            return None
        for eintrag in self.watchlist:
            if str(eintrag.get("name", "")).casefold() == gesucht:
                return eintrag
        if genau:
            return None
        # Auch über einen Suchbegriff finden, z. B. „Pitch Black“ → Set „Dunkelnacht“
        treffer = [e for e in self.watchlist
                   if any(str(b).casefold() == gesucht for b in (e.get("suche") or []))]
        return treffer[0] if len(treffer) == 1 else None

    def _finde(self, name: str):
        if not (name or "").strip():
            raise SteuerFehler("Bitte bei „name“ den Set-Namen eintragen, z. B. Dunkelnacht.")
        eintrag = self._suche_eintrag(name)
        if eintrag is None:
            vorhanden = ", ".join(str(e.get("name")) for e in self.watchlist) or "(Watchlist ist leer)"
            raise SteuerFehler(f"„{name}“ steht nicht auf der Watchlist. Vorhanden: {vorhanden}")
        return eintrag


def sprache_aus_auswahl(text: str | None) -> str | None:
    """Auswahl „sprache“ aus der GitHub-App → DE/EN/JP, oder None für „alle“."""
    sauber = (text or "").strip().lower()
    if sauber in ("", "alle", "egal"):
        return None
    if sauber not in SPRACHEN:
        raise SteuerFehler(f"„{text}“ kenne ich nicht. Möglich sind: alle, DE, EN, JP")
    return SPRACHEN[sauber]


def art_aus_auswahl(text: str | None) -> str | None:
    """Auswahl „produkt“ aus der GitHub-App → Produktart, oder None für „ganzes Set“."""
    if (text or "").strip().lower() in GANZES_SET:
        return None
    art = art_aus_eingabe(text)
    if art is None:
        raise SteuerFehler(f"„{text}“ kenne ich nicht. Möglich sind: ganzes Set, {', '.join(ARTEN)}")
    return art


def beschreibe_max_preis(eintrag: dict) -> str:
    """z. B. „Maximalpreis: ganzes Set 200,00 € · Display DE 180,00 € | 🚨 Chase: Display DE 150,00 €“"""
    teile = []
    if eintrag.get("max_preis") is not None:
        teile.append(f"ganzes Set {euro(float(eintrag['max_preis']))}")
    for schluessel, preis in (eintrag.get("preise") or {}).items():
        teile.append(f"{schluessel} {euro(float(preis))}")
    text = ("Maximalpreis: " + " · ".join(teile)) if teile else "kein Maximalpreis"
    chase = [f"{schluessel} {euro(float(preis))}" for schluessel, preis in (eintrag.get("chase") or {}).items()]
    return text + (" | 🚨 Chase: " + " · ".join(chase) if chase else "")
