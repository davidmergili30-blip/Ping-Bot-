"""Lädt die Einstellungen aus config.yaml und prüft sie.

Wenn etwas nicht stimmt (z. B. ein Tippfehler), gibt es eine verständliche
Fehlermeldung statt eines kryptischen Absturzes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from bot.status import Status

# Standard-Ort der Datei: config.yaml im Hauptordner des Projekts
STANDARD_PFAD = Path(__file__).resolve().parent.parent / "config.yaml"

ERLAUBTE_SPRACHEN = ("DE", "EN", "JP", "egal")
# Ruhezeit im Format "22:00-06:00"
RUHEZEIT_MUSTER = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


class ConfigFehler(Exception):
    """Etwas in config.yaml stimmt nicht. Die Meldung erklärt, was."""


@dataclass
class Allgemein:
    zeitzone: str = "Europe/Berlin"
    user_agent: str = "PokemonPreisBot/0.1 (privater Preisalarm)"
    pause_zwischen_anfragen_sekunden: float = 5
    min_minuten_pro_shop: int = 15
    pausiert: bool = False  # true = der Bot prüft nichts und schickt keine Pings
    robots_txt_beachten: bool = True  # false = robots.txt wird ignoriert (Sperren werden trotzdem nie umgangen)


@dataclass
class Regeln:
    ping_bei_status: list[Status] = field(
        default_factory=lambda: [Status.BESTELLBAR, Status.VORBESTELLBAR]
    )
    max_preis: float | None = None
    min_marge_prozent: float | None = None
    sprache: str = "egal"
    marktplatz_angebote: bool = False
    nur_vertrauenswuerdige_shops: bool = False
    ruhezeit: str | None = None
    in_ruhezeit_nur_dringend: bool = True
    preissturz_prozent: float | None = 10


@dataclass
class Produkt:
    """Ein Eintrag der Watchlist.

    Entweder feste Links zu Produktseiten, oder Suchbegriffe (z. B. ein Set-Name):
    Dann durchsucht der Bot alle unterstützten Shops und beobachtet jedes passende Produkt.
    """

    name: str
    links: list[str]
    regeln: Regeln
    suche: list[str] = field(default_factory=list)


@dataclass
class Kategorie:
    """Eine Shop-Kategorie, die auf neue Produkte und Vorbestellungen überwacht wird."""

    name: str
    link: str


@dataclass
class KategorieFilter:
    nur_mit: list[str] = field(default_factory=list)  # mindestens eins dieser Wörter im Namen
    ohne: list[str] = field(default_factory=list)     # keins dieser Wörter im Namen


@dataclass
class Einstellungen:
    allgemein: Allgemein
    standard_regeln: Regeln
    vertrauenswuerdige_shops: list[str]
    watchlist: list[Produkt] = field(default_factory=list)
    kategorien: list[Kategorie] = field(default_factory=list)
    kategorie_filter: KategorieFilter = field(default_factory=KategorieFilter)
    feeds: list[Kategorie] = field(default_factory=list)  # Deal-Feeds (RSS), z. B. mydealz


def lade_einstellungen(pfad: Path | str = STANDARD_PFAD) -> Einstellungen:
    """Liest config.yaml und gibt geprüfte Einstellungen zurück."""
    try:
        text = Path(pfad).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigFehler(f"Die Datei {pfad} fehlt.") from None

    try:
        daten = yaml.safe_load(text) or {}
    except yaml.YAMLError as fehler:
        markierung = getattr(fehler, "problem_mark", None)
        wo = f" (ungefähr Zeile {markierung.line + 1})" if markierung else ""
        raise ConfigFehler(
            f"config.yaml ist kein gültiges YAML{wo}. Häufige Ursachen: "
            "fehlendes Leerzeichen nach dem Doppelpunkt oder falsche Einrückung."
        ) from None

    if not isinstance(daten, dict):
        raise ConfigFehler("config.yaml muss aus Abschnitten wie 'allgemein:' bestehen.")
    _nur_bekannte(
        daten,
        {"allgemein", "standard_regeln", "vertrauenswuerdige_shops", "watchlist", "kategorien",
         "kategorie_filter", "feeds"},
        "config.yaml",
    )

    standard_regeln = _lese_regeln(daten.get("standard_regeln") or {}, "standard_regeln")
    return Einstellungen(
        allgemein=_lese_allgemein(daten.get("allgemein") or {}),
        standard_regeln=standard_regeln,
        vertrauenswuerdige_shops=_lese_shops(daten.get("vertrauenswuerdige_shops") or []),
        watchlist=_lese_watchlist(daten.get("watchlist") or [], standard_regeln),
        kategorien=_lese_kategorien(daten.get("kategorien") or []),
        kategorie_filter=_lese_filter(daten.get("kategorie_filter") or {}),
        feeds=_lese_kategorien(daten.get("feeds") or [], abschnitt="feeds", art="Feed"),
    )


# ---------------------------------------------------------------------------
# Hilfsfunktionen für die einzelnen Abschnitte
# ---------------------------------------------------------------------------

def _nur_bekannte(daten: dict, erlaubt: set[str], bereich: str) -> None:
    """Meldet unbekannte Einstellungen – meistens sind das Tippfehler."""
    unbekannt = sorted(set(daten) - erlaubt)
    if unbekannt:
        raise ConfigFehler(
            f"Unbekannte Einstellung '{unbekannt[0]}' in {bereich}. "
            f"Erlaubt sind: {', '.join(sorted(erlaubt))}. Vielleicht ein Tippfehler?"
        )


def _abschnitt(wert, bereich: str) -> dict:
    if not isinstance(wert, dict):
        raise ConfigFehler(f"'{bereich}' muss eine Liste von Einstellungen (name: wert) sein.")
    return wert


def _zahl(wert, name: str, bereich: str, *, minimum: float | None = None, leer_erlaubt: bool = False):
    """Prüft, ob wert eine Zahl ist (optional mit Mindestwert)."""
    if wert is None and leer_erlaubt:
        return None
    # Achtung: In Python zählt true/false auch als Zahl – das wollen wir hier nicht.
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        leer = " oder leer (null)" if leer_erlaubt else ""
        raise ConfigFehler(f"'{name}' in {bereich} muss eine Zahl sein{leer}, nicht '{wert}'.")
    if minimum is not None and wert < minimum:
        raise ConfigFehler(f"'{name}' in {bereich} muss mindestens {minimum} sein, nicht {wert}.")
    return wert


def _ja_nein(wert, name: str, bereich: str) -> bool:
    if not isinstance(wert, bool):
        raise ConfigFehler(f"'{name}' in {bereich} muss true oder false sein, nicht '{wert}'.")
    return wert


def _lese_allgemein(daten) -> Allgemein:
    bereich = "allgemein"
    daten = _abschnitt(daten, bereich)
    standard = Allgemein()
    _nur_bekannte(daten, set(vars(standard)), bereich)

    zeitzone = daten.get("zeitzone", standard.zeitzone)
    try:
        ZoneInfo(str(zeitzone))
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigFehler(
            f"Unbekannte Zeitzone '{zeitzone}'. Für Deutschland: Europe/Berlin"
        ) from None

    user_agent = daten.get("user_agent", standard.user_agent)
    if not isinstance(user_agent, str) or not user_agent.strip():
        raise ConfigFehler("'user_agent' in allgemein darf nicht leer sein.")

    return Allgemein(
        zeitzone=str(zeitzone),
        user_agent=user_agent.strip(),
        pause_zwischen_anfragen_sekunden=_zahl(
            daten.get("pause_zwischen_anfragen_sekunden", standard.pause_zwischen_anfragen_sekunden),
            "pause_zwischen_anfragen_sekunden", bereich, minimum=1,
        ),
        # Höflichkeitsregel: jeden Shop höchstens alle 10 Minuten abfragen
        min_minuten_pro_shop=_zahl(
            daten.get("min_minuten_pro_shop", standard.min_minuten_pro_shop),
            "min_minuten_pro_shop", bereich, minimum=10,
        ),
        pausiert=_ja_nein(daten.get("pausiert", standard.pausiert), "pausiert", bereich),
        robots_txt_beachten=_ja_nein(daten.get("robots_txt_beachten", standard.robots_txt_beachten),
                                     "robots_txt_beachten", bereich),
    )


def _lese_regeln(daten, bereich: str, basis: Regeln | None = None) -> Regeln:
    """Liest Regeln. Was fehlt, kommt aus 'basis' (bei Produkten: den Standard-Regeln)."""
    daten = _abschnitt(daten, bereich)
    standard = basis or Regeln()
    _nur_bekannte(daten, set(vars(standard)), bereich)

    # Welche Status sollen einen Ping auslösen?
    roh_status = daten.get("ping_bei_status", [s.value for s in standard.ping_bei_status])
    if not isinstance(roh_status, list):
        raise ConfigFehler(
            f"'ping_bei_status' in {bereich} muss eine Liste sein, z. B. [BESTELLBAR, VORBESTELLBAR]."
        )
    ping_bei_status = []
    for eintrag in roh_status:
        try:
            ping_bei_status.append(Status(str(eintrag).upper()))
        except ValueError:
            gueltig = ", ".join(s.value for s in Status)
            raise ConfigFehler(
                f"Unbekannter Status '{eintrag}' in {bereich}. Gültig sind: {gueltig}"
            ) from None

    sprache = str(daten.get("sprache", standard.sprache))
    sprache = "egal" if sprache.lower() == "egal" else sprache.upper()
    if sprache not in ERLAUBTE_SPRACHEN:
        raise ConfigFehler(
            f"'sprache' in {bereich} muss eins davon sein: {', '.join(ERLAUBTE_SPRACHEN)}"
        )

    ruhezeit = daten.get("ruhezeit", standard.ruhezeit)
    if ruhezeit is not None and not RUHEZEIT_MUSTER.match(str(ruhezeit)):
        raise ConfigFehler(
            f"'ruhezeit' in {bereich} muss so aussehen: \"22:00-06:00\" (mit Anführungszeichen) oder null."
        )

    return Regeln(
        ping_bei_status=ping_bei_status,
        max_preis=_zahl(daten.get("max_preis", standard.max_preis), "max_preis", bereich,
                        minimum=0, leer_erlaubt=True),
        min_marge_prozent=_zahl(
            daten.get("min_marge_prozent", standard.min_marge_prozent), "min_marge_prozent", bereich,
            leer_erlaubt=True,
        ),
        sprache=sprache,
        marktplatz_angebote=_ja_nein(
            daten.get("marktplatz_angebote", standard.marktplatz_angebote), "marktplatz_angebote", bereich
        ),
        nur_vertrauenswuerdige_shops=_ja_nein(
            daten.get("nur_vertrauenswuerdige_shops", standard.nur_vertrauenswuerdige_shops),
            "nur_vertrauenswuerdige_shops", bereich,
        ),
        ruhezeit=None if ruhezeit is None else str(ruhezeit),
        in_ruhezeit_nur_dringend=_ja_nein(
            daten.get("in_ruhezeit_nur_dringend", standard.in_ruhezeit_nur_dringend),
            "in_ruhezeit_nur_dringend", bereich,
        ),
        preissturz_prozent=_zahl(
            daten.get("preissturz_prozent", standard.preissturz_prozent), "preissturz_prozent", bereich,
            minimum=1, leer_erlaubt=True,
        ),
    )


def _lese_shops(daten) -> list[str]:
    """Whitelist der vertrauenswürdigen Shops, z. B. ['mediamarkt.de', 'mueller.de']."""
    if not isinstance(daten, list):
        raise ConfigFehler("'vertrauenswuerdige_shops' muss eine Liste sein (jede Zeile mit '- ').")
    shops = []
    for eintrag in daten:
        if not isinstance(eintrag, str) or not eintrag.strip():
            raise ConfigFehler(f"Ungültiger Eintrag in vertrauenswuerdige_shops: '{eintrag}'")
        shop = eintrag.strip().lower().removeprefix("https://").removeprefix("http://")
        shops.append(shop.removeprefix("www.").rstrip("/"))
    return shops


def _link(wert, wo: str) -> str:
    if not isinstance(wert, str) or not wert.strip().startswith(("https://", "http://")):
        raise ConfigFehler(f"{wo}: '{wert}' ist kein Link. Links beginnen mit https://")
    return wert.strip()


def _name(eintrag: dict, wo: str) -> str:
    name = eintrag.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigFehler(f"{wo} braucht einen 'name', z. B.  name: \"Display Set XY (DE)\"")
    return name.strip()


def _lese_watchlist(daten, standard_regeln: Regeln) -> list[Produkt]:
    if not isinstance(daten, list) or not all(isinstance(p, dict) for p in daten):
        raise ConfigFehler("'watchlist' muss eine Liste von Produkten sein (jedes beginnt mit '- name: ').")
    regel_felder = set(vars(standard_regeln))
    produkte = []
    for nr, eintrag in enumerate(daten, start=1):
        name = _name(eintrag, f"Produkt Nr. {nr} der watchlist")
        wo = f"watchlist '{name}'"
        _nur_bekannte(eintrag, {"name", "links", "suche"} | regel_felder, wo)
        links = eintrag.get("links") or []
        suche = eintrag.get("suche") or []
        if not isinstance(links, list) or not isinstance(suche, list) or not (links or suche):
            raise ConfigFehler(
                f"{wo} braucht 'links:' (Produkt-Links) oder 'suche:' (Suchbegriffe, z. B. Set-Namen), "
                "jeweils als Liste mit '- ' am Zeilenanfang."
            )
        if not all(isinstance(s, (str, int)) and str(s).strip() for s in suche):
            raise ConfigFehler(f"{wo}: Jeder Suchbegriff muss ein Text sein, z. B.  - Dunkelnacht")
        # Alles außer name/links/suche sind Regeln, die nur für dieses Produkt gelten
        eigene_regeln = {k: v for k, v in eintrag.items() if k in regel_felder}
        produkte.append(Produkt(
            name=name,
            links=[_link(link, wo) for link in links],
            regeln=_lese_regeln(eigene_regeln, wo, basis=standard_regeln),
            suche=[str(s).strip() for s in suche],
        ))
    return produkte


def _lese_kategorien(daten, abschnitt: str = "kategorien", art: str = "Kategorie") -> list[Kategorie]:
    if not isinstance(daten, list) or not all(isinstance(k, dict) for k in daten):
        raise ConfigFehler(f"'{abschnitt}' muss eine Liste sein (jeder Eintrag beginnt mit '- name: ').")
    kategorien = []
    for nr, eintrag in enumerate(daten, start=1):
        name = _name(eintrag, f"{art} Nr. {nr}")
        _nur_bekannte(eintrag, {"name", "link"}, f"{art} '{name}'")
        kategorien.append(Kategorie(name=name, link=_link(eintrag.get("link"), f"{art} '{name}'")))
    return kategorien


def _lese_filter(daten) -> KategorieFilter:
    daten = _abschnitt(daten, "kategorie_filter")
    _nur_bekannte(daten, {"nur_mit", "ohne"}, "kategorie_filter")
    woerter = {}
    for feld in ("nur_mit", "ohne"):
        liste = daten.get(feld) or []
        if not isinstance(liste, list) or not all(isinstance(w, (str, int)) for w in liste):
            raise ConfigFehler(f"'{feld}' in kategorie_filter muss eine Liste von Wörtern sein.")
        woerter[feld] = [str(w).strip() for w in liste if str(w).strip()]
    return KategorieFilter(**woerter)
