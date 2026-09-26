"""Die Datenbank des Bots (SQLite – eine einzige Datei, kein Server nötig).

Hier merkt sich der Bot:
- jeden Check (Preis- und Statusverlauf)
- den letzten bekannten Stand pro Produkt (damit er nur bei Änderungen pingt)
- wann ein Shop zuletzt abgefragt wurde und ob er gerade blockt
- Kleinkram wie die letzte gelesene Discord-Nachricht

Auf GitHub wird die Datei zwischen den Läufen im Cache aufbewahrt.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.adapter.basis import CheckErgebnis
from bot.status import Status

STANDARD_PFAD = Path(__file__).resolve().parent.parent / "daten" / "bot.db"

TABELLEN = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    zeit TEXT NOT NULL,
    url TEXT NOT NULL,
    shop TEXT NOT NULL,
    produkt TEXT,
    status TEXT NOT NULL,
    preis REAL,
    verkaeufer TEXT,
    versand REAL,
    mengenlimit INTEGER,
    liefertermin TEXT,
    hinweis TEXT
);
CREATE INDEX IF NOT EXISTS checks_url ON checks (url, zeit);

CREATE TABLE IF NOT EXISTS stand (
    url TEXT PRIMARY KEY,
    shop TEXT NOT NULL,
    produkt TEXT,
    status TEXT NOT NULL,
    preis REAL,
    seit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shops (
    domain TEXT PRIMARY KEY,
    letzter_abruf TEXT,
    blockiert INTEGER NOT NULL DEFAULT 0,
    grund TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    schluessel TEXT PRIMARY KEY,
    wert TEXT
);
"""


def jetzt_utc() -> datetime:
    return datetime.now(timezone.utc)


class Speicher:
    def __init__(self, pfad: Path | str = STANDARD_PFAD):
        Path(pfad).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(pfad))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(TABELLEN)
        self._db.commit()

    def schliessen(self) -> None:
        self._db.close()

    # --- Checks (Verlauf) ------------------------------------------------------

    def speichere_check(self, url: str, shop: str, produkt: str | None, e: CheckErgebnis,
                        zeit: datetime | None = None) -> None:
        self._db.execute(
            "INSERT INTO checks (zeit, url, shop, produkt, status, preis, verkaeufer, versand,"
            " mengenlimit, liefertermin, hinweis) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ((zeit or jetzt_utc()).isoformat(), url, shop, produkt, e.status.value, e.preis,
             e.verkaeufer, e.versand, e.mengenlimit, e.liefertermin, e.hinweis),
        )
        self._db.commit()

    def anzahl_checks(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM checks").fetchone()[0]

    # --- Letzter bekannter Stand pro Produkt -------------------------------------

    def stand(self, url: str) -> tuple[Status, float | None] | None:
        """Letzter bekannter Status und Preis – oder None, wenn das Produkt neu ist."""
        zeile = self._db.execute("SELECT status, preis FROM stand WHERE url = ?", (url,)).fetchone()
        return (Status(zeile["status"]), zeile["preis"]) if zeile else None

    def setze_stand(self, url: str, shop: str, produkt: str | None, status: Status,
                    preis: float | None, zeit: datetime | None = None) -> None:
        self._db.execute(
            "INSERT INTO stand (url, shop, produkt, status, preis, seit) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(url) DO UPDATE SET shop=excluded.shop, produkt=excluded.produkt,"
            " status=excluded.status, preis=excluded.preis, seit=excluded.seit",
            (url, shop, produkt, status.value, preis, (zeit or jetzt_utc()).isoformat()),
        )
        self._db.commit()

    # --- Shops: letzter Abruf und Blockaden ----------------------------------------

    def letzter_abruf(self, domain: str) -> datetime | None:
        zeile = self._db.execute("SELECT letzter_abruf FROM shops WHERE domain = ?", (domain,)).fetchone()
        return datetime.fromisoformat(zeile[0]) if zeile and zeile[0] else None

    def setze_abruf(self, domain: str, zeit: datetime | None = None) -> None:
        self._db.execute(
            "INSERT INTO shops (domain, letzter_abruf) VALUES (?, ?)"
            " ON CONFLICT(domain) DO UPDATE SET letzter_abruf = excluded.letzter_abruf",
            (domain, (zeit or jetzt_utc()).isoformat()),
        )
        self._db.commit()

    def blockade(self, domain: str) -> str | None:
        """Grund der gemeldeten Blockade – oder None, wenn der Shop nicht als blockiert gilt."""
        zeile = self._db.execute("SELECT blockiert, grund FROM shops WHERE domain = ?", (domain,)).fetchone()
        return zeile["grund"] if zeile and zeile["blockiert"] else None

    def setze_blockade(self, domain: str, grund: str | None) -> None:
        """grund=None hebt die Blockade wieder auf."""
        self._db.execute(
            "INSERT INTO shops (domain, blockiert, grund) VALUES (?, ?, ?)"
            " ON CONFLICT(domain) DO UPDATE SET blockiert = excluded.blockiert, grund = excluded.grund",
            (domain, 1 if grund else 0, grund),
        )
        self._db.commit()

    # --- Sonstiges -----------------------------------------------------------------

    def meta(self, schluessel: str) -> str | None:
        zeile = self._db.execute("SELECT wert FROM meta WHERE schluessel = ?", (schluessel,)).fetchone()
        return zeile[0] if zeile else None

    def setze_meta(self, schluessel: str, wert: str | None) -> None:
        self._db.execute(
            "INSERT INTO meta (schluessel, wert) VALUES (?, ?)"
            " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
            (schluessel, wert),
        )
        self._db.commit()
