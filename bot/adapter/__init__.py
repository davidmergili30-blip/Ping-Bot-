"""Alle Shop-Adapter an einem Ort.

Neuen Shop hinzufügen: Adapter schreiben (oder JtlShop wiederverwenden, wenn der
Shop mit JTL-Shop läuft) und unten in ADAPTER eintragen.
"""

from __future__ import annotations

from bot.adapter.basis import CheckErgebnis, ListenEintrag, ShopAdapter, domain_von
from bot.adapter.games_island import GamesIsland
from bot.adapter.jtl import JtlShop

ADAPTER: list[ShopAdapter] = [
    JtlShop("Gate to the Games", ("gate-to-the-games.de",), treffer_pro_seite=100),
    JtlShop("Card-Corner", ("card-corner.de",), treffer_pro_seite=50),
    GamesIsland(),  # über crawlme.games-island.eu, die offizielle Datenquelle für Programme
]

# Shops, die automatisches Abfragen ausdrücklich verbieten – hier fragt der Bot nie an.
NICHT_ERLAUBT: dict[str, str] = {
    # Geprüft am 27.09.2026 – diese Shops sperren automatische Abfragen. Der Bot umgeht das nicht.
    "rossmann.de": (
        "Rossmann verbietet die Suche in der robots.txt und zeigt Bot-Schutz („Client Challenge“)."
    ),
    "smythstoys.com": "Smyths Toys blockt automatische Abfragen (HTTP 403).",
    "netto-online.de": "Netto blockt automatische Abfragen (Access Denied – sogar für die robots.txt).",
}


def adapter_fuer(url: str) -> ShopAdapter | None:
    return next((a for a in ADAPTER if a.passt_zu(url)), None)


__all__ = ["ADAPTER", "NICHT_ERLAUBT", "CheckErgebnis", "ListenEintrag", "ShopAdapter", "adapter_fuer", "domain_von"]
