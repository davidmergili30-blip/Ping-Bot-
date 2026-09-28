"""Was für ein Produkt ist das? Art, Set und Sprache aus dem Produktnamen lesen.

Gebraucht für:
- Maximalpreise je Produkt (z. B. „Dunkelnacht – Display: 180 €“)
- den Preisvergleich zwischen Shops (gleiches Set + gleiche Art + gleiche Sprache)
- das Erkennen neuer Sets im Vorverkauf

Shops schreiben Namen sehr unterschiedlich („Top Trainer Box“, „Top-Trainer-Box“, „Elite Trainer Box“,
„ETB“ …). Deshalb wird der Name vorher vereinfacht: klein, ohne Bindestriche und Sonderzeichen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # nur für die Typ-Angaben – vermeidet einen Kreis-Import mit einstellungen.py
    from bot.einstellungen import Produkt, Regeln

# Die Produktarten, für die man eigene Maximalpreise setzen kann (in dieser Schreibweise angezeigt)
ARTEN = ("Display", "Top-Trainer-Box", "Booster Bundle", "Mini-Tin", "Mini-Tin-Display", "Kollektion")

# Was man in der GitHub-App oder in config.yaml eintippen darf → Produktart
_EINGABEN = {
    "display": "Display", "displays": "Display", "booster display": "Display",
    "top trainer box": "Top-Trainer-Box", "top trainer boxen": "Top-Trainer-Box", "top trainer": "Top-Trainer-Box",
    "ttb": "Top-Trainer-Box", "elite trainer box": "Top-Trainer-Box", "elite trainer": "Top-Trainer-Box",
    "etb": "Top-Trainer-Box",
    "booster bundle": "Booster Bundle", "booster bundles": "Booster Bundle", "bundle": "Booster Bundle",
    "mini tin": "Mini-Tin", "mini tins": "Mini-Tin", "minitin": "Mini-Tin", "minitins": "Mini-Tin",
    "mini tin display": "Mini-Tin-Display", "mini tins display": "Mini-Tin-Display",
    "mini tin displays": "Mini-Tin-Display", "minitin display": "Mini-Tin-Display",
    "kollektion": "Kollektion", "kollektionen": "Kollektion", "collection": "Kollektion",
    "collections": "Kollektion",
}

# Sonderformen: nicht mit dem „normalen“ Produkt vergleichbar (anderer Inhalt oder andere Menge)
_SONDERFORMEN = re.compile(
    r"\b(18er|18 booster|case|pokemon center|set|differenzbesteuert|beschaedigt|beschädigt|zufaellig|zufällig|"
    r"jede tin|bundle display|b ware)\b")


def vereinfacht(text: str | None) -> str:
    """'Top-Trainer-Box (deutsch)' → 'top trainer box deutsch'"""
    text = (text or "").lower().replace("é", "e")
    text = re.sub(r"[^\w&]+", " ", text)
    return " ".join(text.split())


def art_aus_eingabe(text: str | None) -> str | None:
    """Eingabe wie „ttb“ oder „Top Trainer Box“ → „Top-Trainer-Box“. Unbekannt → None."""
    return _EINGABEN.get(vereinfacht(text))


def produktart(titel: str | None) -> str | None:
    """Welche Art Produkt ist das? None = keine der bekannten Arten."""
    t = vereinfacht(titel)
    worte = set(t.split())
    mini_tin = re.search(r"\bmini ?tins?\b", t) is not None
    display = "display" in worte or "displays" in worte
    if mini_tin and display:
        return "Mini-Tin-Display"
    if re.search(r"\b(top|elite) trainer\b|\betb\b|\bttb\b", t):
        return "Top-Trainer-Box"
    if "booster bundle" in t:
        return "Display" if display else "Booster Bundle"  # „Booster Bundle Display“ = ganzer Karton
    if mini_tin:
        return "Mini-Tin"
    if display:
        return "Display"
    if worte & {"kollektion", "collection"} or re.search(r"kollektion\b", t):
        return "Kollektion"
    return None


def sonderform(titel: str | None) -> bool:
    """True bei 18er-Displays, Cases, Pokémon-Center-Editionen, Sets aus mehreren Produkten usw."""
    return _SONDERFORMEN.search(vereinfacht(titel)) is not None


def set_fuer(titel: str | None, watchlist: list[Produkt]) -> tuple[Produkt, str] | None:
    """Zu welchem Set der Watchlist gehört der Titel? Gibt (Set, gefundener Suchbegriff) zurück."""
    t = f" {vereinfacht(titel)} "
    for produkt in watchlist:
        for begriff in produkt.suche:
            if f" {vereinfacht(begriff)} " in t:
                return produkt, begriff
    return None


def sprache(titel: str | None, begriff: str, set_name: str) -> str:
    """DE, EN oder JP – aus dem Namen. Ohne Angabe: deutscher Set-Name = DE, sonst EN."""
    roh = (titel or "").lower()
    t = f" {vereinfacht(titel)} "
    if re.search(r" (koreanisch|korean|kr) ", t):
        return "KR"
    if re.search(r" (chinesisch|chinese|cn|s chinese|t chinese) ", t):
        return "CN"
    # Japanische Sets haben bei manchen Shops nur ein Kürzel wie (M5) oder (M6a)
    if re.search(r" (japanisch|japanese|japan|jp|jap) ", t) or re.search(r"\(m\d+[a-z]?\)", roh):
        return "JP"
    if re.search(r" (englisch|english|en|eng) ", t):
        return "EN"
    if re.search(r" (deutsch|german|de|ger) ", t):
        return "DE"
    return "DE" if vereinfacht(begriff) == vereinfacht(set_name) else "EN"


def vergleichs_schluessel(titel: str | None, watchlist: list[Produkt]) -> tuple[str, str, str] | None:
    """(Set, Art, Sprache) – gleich bei gleichem Produkt in verschiedenen Shops. None = nicht vergleichbar."""
    treffer = set_fuer(titel, watchlist)
    art = produktart(titel)
    # Kollektionen und einzelne Mini-Tins gibt es pro Set in vielen Varianten → nicht eindeutig
    if treffer is None or art in (None, "Kollektion", "Mini-Tin") or sonderform(titel):
        return None
    produkt, begriff = treffer
    return produkt.name, art, sprache(titel, begriff, produkt.name)


# --- Preise je Produkt -------------------------------------------------------------------

SPRACHEN = {"de": "DE", "deutsch": "DE", "en": "EN", "englisch": "EN", "english": "EN",
            "jp": "JP", "japanisch": "JP", "japanese": "JP"}
# Wörter, die nur die Produktart beschreiben (alles andere in einem Preis-Schlüssel muss im Namen stehen)
_ART_WOERTER = {"display", "displays", "booster", "top", "trainer", "box", "boxen", "elite", "etb", "ttb", "bundle",
                "bundles", "mini", "tin", "tins", "minitin", "minitins", "kollektion", "kollektionen", "collection",
                "collections"}


@dataclass(frozen=True)
class PreisSchluessel:
    """Für welche Produkte gilt ein Preis? z. B. „Display DE“, „Top-Trainer-Box“, „Poster Kollektion“, „18er Display“."""

    art: str
    sprache: str | None = None           # None = alle Sprachen
    woerter: tuple[str, ...] = ()        # zusätzliche Wörter, die im Produktnamen stehen müssen

    @property
    def text(self) -> str:
        """Einheitliche Schreibweise für config.yaml, z. B. „Display DE“."""
        teile = [*self.woerter, self.art] if self.woerter else [self.art]
        return " ".join(teile) + (f" {self.sprache}" if self.sprache else "")

    @property
    def genauigkeit(self) -> tuple[int, int]:
        """Je genauer, desto mehr Vorrang: erst Zusatzwörter, dann Sprache."""
        return len(self.woerter), 1 if self.sprache else 0


def preis_schluessel(text: str | None) -> PreisSchluessel | None:
    """„Display DE“ → (Display, DE); „Premium Poster Kollektion“ → (Kollektion, alle, premium+poster). Unklar → None."""
    worte = vereinfacht(text).split()
    sprache_ = SPRACHEN.get(worte[-1]) if worte else None
    if sprache_:
        worte = worte[:-1]
    rest = " ".join(worte)
    art = _EINGABEN.get(rest) or produktart(rest)
    if art is None:
        return None
    zusatz = () if rest in _EINGABEN else tuple(w for w in worte if w not in _ART_WOERTER)
    return PreisSchluessel(art=art, sprache=sprache_, woerter=zusatz)


def _passender_preis(tabelle: dict[str, float], titel: str | None, art: str, sprache_: str,
                     nur_genaue_bei_sonderform: bool) -> float | None:
    """Der Preis aus der Tabelle, dessen Schlüssel am genauesten auf das Produkt passt."""
    worte = set(vereinfacht(titel).split())
    sonder = sonderform(titel)
    beste: tuple[tuple[int, int], float] | None = None
    for text, preis in tabelle.items():
        s = preis_schluessel(text)
        if s is None or s.art != art or (s.sprache and s.sprache != sprache_):
            continue
        if not set(s.woerter) <= worte:
            continue
        # Chasepreis: Sonderformen (18er-Display, Pokémon-Center-Edition, Case …) nur mit eigenem Schlüssel –
        # sonst würde z. B. ein halbes Display wegen seines halben Preises als „Chase“ gemeldet
        if nur_genaue_bei_sonderform and sonder and not s.woerter:
            continue
        if beste is None or s.genauigkeit > beste[0]:
            beste = (s.genauigkeit, preis)
    return beste[1] if beste else None


def regeln_fuer(titel: str | None, watchlist: list[Produkt], standard: Regeln,
                produkt: Produkt | None = None) -> Regeln:
    """Regeln für genau dieses Produkt.

    Maximalpreis: genauester passender Eintrag bei „preise“ (z. B. „Display DE“) > Preis fürs ganze Set > Standard.
    Chasepreis: genauester passender Eintrag bei „chase“ – sonst keiner.
    produkt: das Set, falls schon bekannt (bei der Set-Suche) – sonst wird es am Namen erkannt.
    """
    treffer = set_fuer(titel, [produkt] if produkt is not None else watchlist)
    if produkt is None:
        if treffer is None:
            return standard
        produkt = treffer[0]
    art = produktart(titel)
    if art is None:
        return produkt.regeln
    begriff = treffer[1] if treffer else produkt.name
    sprache_ = sprache(titel, begriff, produkt.name)
    regeln = produkt.regeln
    max_preis = _passender_preis(produkt.preise, titel, art, sprache_, nur_genaue_bei_sonderform=False)
    if max_preis is not None:
        regeln = replace(regeln, max_preis=max_preis)
    chase = _passender_preis(produkt.chase, titel, art, sprache_, nur_genaue_bei_sonderform=True)
    if chase is not None:
        regeln = replace(regeln, chase_preis=chase)
    return regeln


# --- Neue Sets erkennen -------------------------------------------------------------------

_ART_WORT = re.compile(
    r"\b(display|booster[ -]display|top[ -]trainer|elite[ -]trainer|etb|booster[ -]bundle|booster[ -]box|"
    r"mini[ -]?tins?|"
    r"kollektion|collection|18er|36er|build (?:&|and|und) battle)", re.I)
_VORSILBEN = re.compile(
    r"^(pok[eé]mon|tcg|sammelkartenspiel|trading card game|expansion|karmesin (?:&|und) purpur|"
    r"scarlet (?:&|and) violet|schwert (?:&|und) schild|sword (?:&|and) shield|mega[ -]entwicklung|"
    r"mega[ -]evolution|kp\d+|sv\d+[a-z]*|me\d+[a-z]*)[\s:–-]*", re.I)
_NACHSILBEN = re.compile(r"[\s:–-]*(expansion|set|sammelkartenspiel)$", re.I)


# Andere Sammelkartenspiele – deren Sets sollen nie vorgeschlagen werden
_ANDERE_SPIELE = re.compile(
    r"\b(mtg|magic|one piece|yu ?gi ?oh|lorcana|digimon|dragon ball|flesh (?:and|&) blood|star wars|riftbound|"
    r"gundam|weiss schwarz|union arena|sorcery|altered|universes beyond)\b", re.I)


def set_name_aus_titel(titel: str | None) -> str | None:
    """'Mega-Entwicklung Delta Herrschaft Display (36 Booster) (deutsch) VORVERKAUF' → 'Delta Herrschaft'"""
    if _ANDERE_SPIELE.search(titel or "") or re.search(r"\btins?\b", titel or "", re.I):
        return None  # anderes Kartenspiel – oder Tin-Displays („Pokéball Tins Herbst 2025“ ist kein Set)
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", titel or "")
    text = re.sub(r"\bvorverkauf\b", " ", text, flags=re.I)
    art = _ART_WORT.search(text)
    if art is None:
        return None
    text = text[:art.start()]
    text = re.split(r":| - | – ", text)[-1]  # „Pokemon TCG - Mega-Entwicklung 02.5: Name“ → „ Name“
    text = " ".join(text.split())
    vorher = None
    while vorher != text:  # Vorsilben wie „Pokemon“, „Mega-Entwicklung“, „02.5:“ nacheinander entfernen
        vorher = text
        text = _VORSILBEN.sub("", text).strip()
        text = _NACHSILBEN.sub("", text).strip()
    if not (2 <= len(text) <= 40) or not re.search(r"[a-zäöüß]", text, re.I) or len(text.split()) > 5:
        return None
    return text
