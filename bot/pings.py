"""Entscheidet, WANN du einen Ping bekommst, und baut die Discord-Kästen dafür.

Grundregel: Ping nur bei Änderungen – z. B. AUSVERKAUFT → BESTELLBAR,
BALD → VORBESTELLBAR oder ein deutlicher Preissturz. Kein Spam, wenn sich
nichts getan hat.
"""

from __future__ import annotations

from bot.adapter.basis import CheckErgebnis
from bot.discord import Kasten
from bot.einstellungen import Regeln
from bot.status import Status

EMOJI = {
    Status.BESTELLBAR: "🟢",
    Status.VORBESTELLBAR: "🔵",
    Status.NUR_EINLADUNG: "🟡",
    Status.NUR_MARKTPLATZ: "🟠",
    Status.NUR_FILIALE: "🏬",
    Status.BALD: "⏳",
    Status.AUSVERKAUFT: "🔴",
    Status.UNBEKANNT: "❔",
}

FARBE = {
    Status.BESTELLBAR: 0x2ECC71,     # grün
    Status.VORBESTELLBAR: 0x3498DB,  # blau
    Status.NUR_EINLADUNG: 0xF1C40F,  # gelb
    Status.NUR_MARKTPLATZ: 0xE67E22, # orange
    Status.NUR_FILIALE: 0x9B59B6,    # lila
    Status.BALD: 0x95A5A6,           # grau
    Status.AUSVERKAUFT: 0xE74C3C,    # rot
    Status.UNBEKANNT: 0x7F8C8D,      # dunkelgrau
}
FARBE_WARNUNG = 0xF39C12
FARBE_INFO = 0x95A5A6

LESBAR = {
    Status.NUR_EINLADUNG: "NUR AUF EINLADUNG",
    Status.NUR_MARKTPLATZ: "NUR MARKTPLATZ",
    Status.NUR_FILIALE: "NUR IN DER FILIALE",
    Status.BALD: "BALD VERFÜGBAR",
}


def lesbar(status: Status) -> str:
    return LESBAR.get(status, status.value)


def euro(preis: float | None) -> str:
    """199.9 -> '199,90 €'"""
    if preis is None:
        return "Preis noch offen"
    return f"{preis:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def preis_text(e: CheckErgebnis) -> str:
    """Preis für die Nachricht. Manche Quellen nennen keine Preise (z. B. Games Island)."""
    if e.preis is None and e.ohne_preis:
        return "Preis im Shop"
    return euro(e.preis)


def ping_grund(alt: tuple[Status, float | None] | None, neu: CheckErgebnis, regeln: Regeln,
               shop_vertraut: bool) -> str | None:
    """Gibt zurück, WARUM gepingt werden soll – oder None.

    Mögliche Gründe: 'neu', 'status', 'unter_maximalpreis', 'preissturz'
    """
    if neu.status == Status.UNBEKANNT:
        return None  # Lieber nichts sagen als raten
    if neu.status not in regeln.ping_bei_status:
        return None
    if regeln.max_preis is not None and neu.preis is not None and neu.preis > regeln.max_preis:
        return None
    if neu.status == Status.NUR_MARKTPLATZ and not regeln.marktplatz_angebote:
        return None
    if regeln.nur_vertrauenswuerdige_shops and not shop_vertraut:
        return None
    if alt is None:
        return "neu"
    alt_status, alt_preis = alt
    if alt_status != neu.status:
        return "status"
    if (regeln.max_preis is not None and alt_preis is not None and neu.preis is not None
            and alt_preis > regeln.max_preis >= neu.preis):
        return "unter_maximalpreis"
    if (regeln.preissturz_prozent and alt_preis and neu.preis
            and neu.preis <= alt_preis * (1 - regeln.preissturz_prozent / 100)):
        return "preissturz"
    return None


def ping_kasten(produkt: str, shop: str, url: str, neu: CheckErgebnis, alt: tuple[Status, float | None] | None,
                grund: str, shop_vertraut: bool, aus_kategorie: bool = False) -> Kasten:
    """Baut den Discord-Kasten für einen Ping."""
    if grund == "preissturz":
        titel = f"📉 PREISSTURZ – {produkt}"
    elif grund == "unter_maximalpreis":
        titel = f"💶 UNTER DEINEM MAXIMALPREIS – {produkt}"
    else:
        titel = f"{EMOJI[neu.status]} {lesbar(neu.status)} – {produkt}"

    zeilen = [f"**{shop}** · {preis_text(neu)}" + (" (Verkauf durch Shop)" if neu.verkaeufer == "Shop" else "")]
    if neu.liefertermin:
        zeilen.append(f"📅 Liefertermin: {neu.liefertermin}")
    if neu.mengenlimit:
        zeilen.append(f"🔢 Max. {neu.mengenlimit} Stück pro Bestellung")
    if neu.versand is not None:
        zeilen.append(f"🚚 Versand: {euro(neu.versand)}")

    if grund in ("preissturz", "unter_maximalpreis") and alt and alt[1]:
        prozent = round((1 - neu.preis / alt[1]) * 100)
        zeilen.append(f"Vorher: {euro(alt[1])} (−{prozent} %)")
    elif alt is not None:
        zeilen.append(f"Vorher: {lesbar(alt[0])}")
    elif aus_kategorie:
        zeilen.append("🆕 Neu im Shop entdeckt")
    else:
        zeilen.append("Erster Check dieses Produkts")

    if not shop_vertraut:
        zeilen.append("⚠️ Shop ist nicht auf deiner Vertrauensliste")
    zeilen.append("👉 Tipp auf die Überschrift, um zum Shop zu gehen")
    return Kasten(titel=titel, text="\n".join(zeilen), link=url, farbe=FARBE[neu.status])


def zusammenfassung(kaesten: list[Kasten]) -> str:
    """Kurzer Text über den Kästen – den zeigt das iPhone in der Mitteilung an."""
    if not kaesten:
        return ""
    erste = kaesten[0].titel
    rest = len(kaesten) - 1
    return erste + (f" (+{rest} weitere)" if rest else "")
