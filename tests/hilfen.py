"""Hilfsfunktionen für die Tests."""

from bs4 import BeautifulSoup


def ohne_ausverkauft_markierung(html: str) -> str:
    """Entfernt den „Ausverkauft“-Banner aus einer Seite.

    So wird aus einer (echten) ausverkauften Vorbestellung eine noch bestellbare –
    damit lässt sich die Erkennung von VORBESTELLBAR testen.
    """
    soup = BeautifulSoup(html, "html.parser")
    for banner in soup.select(".ribbon-7"):
        banner.decompose()
    return str(soup)
