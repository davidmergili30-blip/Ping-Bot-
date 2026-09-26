"""Alle Shop-Adapter an einem Ort.

Neuen Shop hinzufügen: Adapter schreiben (oder JtlShop wiederverwenden, wenn der
Shop mit JTL-Shop läuft) und unten in ADAPTER eintragen.
"""

from __future__ import annotations

from bot.adapter.basis import CheckErgebnis, ListenEintrag, ShopAdapter, domain_von
from bot.adapter.jtl import JtlShop

ADAPTER: list[ShopAdapter] = [
    JtlShop("Gate to the Games", ("gate-to-the-games.de",)),
    JtlShop("Card-Corner", ("card-corner.de",)),
]

# Shops, die automatisches Abfragen ausdrücklich verbieten – hier fragt der Bot nie an.
NICHT_ERLAUBT: dict[str, str] = {
    "games-island.eu": (
        "Games Island verbietet automatisches Abfragen (robots.txt – auch für crawlme.games-island.eu). "
        "Tipp: Tritt ihrem Discord „Games Island Hof“ bei (siehe Anleitung)."
    ),
}


def adapter_fuer(url: str) -> ShopAdapter | None:
    return next((a for a in ADAPTER if a.passt_zu(url)), None)


__all__ = ["ADAPTER", "NICHT_ERLAUBT", "CheckErgebnis", "ListenEintrag", "ShopAdapter", "adapter_fuer", "domain_von"]
