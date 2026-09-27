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
        self.watchlist.append(eintrag)
        return eintrag

    def set_entfernen(self, name: str) -> dict:
        eintrag = self._finde(name)
        self.watchlist.remove(eintrag)
        return eintrag

    def max_preis(self, name: str, preis: float | None) -> dict:
        eintrag = self._finde(name)
        if preis is None:
            eintrag.pop("max_preis", None)
        else:
            eintrag["max_preis"] = int(preis) if float(preis).is_integer() else preis
        return eintrag

    def pause(self, an: bool) -> None:
        self.daten["allgemein"]["pausiert"] = an

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


def beschreibe_max_preis(eintrag: dict) -> str:
    preis = eintrag.get("max_preis")
    return euro(float(preis)) if preis is not None else "kein Maximalpreis"
