"""Alle Status, die ein Produkt-Check ergeben kann.

Jeder Shop-Check endet mit genau einem dieser Werte.
Lieber UNBEKANNT als falsch raten!
"""

from enum import Enum


class Status(str, Enum):
    BESTELLBAR = "BESTELLBAR"          # Auf Lager, direkt kaufbar, Verkauf durch den Shop selbst
    VORBESTELLBAR = "VORBESTELLBAR"    # Vorbestellung möglich (mit Liefertermin)
    NUR_EINLADUNG = "NUR_EINLADUNG"    # Nur „auf Einladung anfordern“ (z. B. Amazon)
    NUR_MARKTPLATZ = "NUR_MARKTPLATZ"  # Nur über Drittanbieter / Marktplatz-Händler
    NUR_FILIALE = "NUR_FILIALE"        # Nur im Laden / Abholung, nicht online bestellbar
    BALD = "BALD"                      # „Bald verfügbar“ / „Benachrichtigen“
    AUSVERKAUFT = "AUSVERKAUFT"        # Nicht verfügbar
    UNBEKANNT = "UNBEKANNT"            # Nicht sicher erkannt oder die Seite blockt
