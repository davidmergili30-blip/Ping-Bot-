"""Macht gespeicherte Shop-Seiten kleiner, damit sie als Testbeispiele ins Repo passen.

Entfernt nur Dinge, die für die Status-Erkennung egal sind: Skripte, Styles,
Grafiken und Kommentare. Aufruf: python tests/beispiele/verkleinern.py <quelle> <ziel>
"""

import sys

from bs4 import BeautifulSoup, Comment


def verkleinern(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(["script", "style", "svg", "noscript", "iframe", "picture", "img", "link", "meta"]):
        if el.decomposed:  # steckte in einem schon entfernten Element
            continue
        # schema.org-Angaben (meta/link mit itemprop) und JSON-LD bleiben erhalten
        if el.get("itemprop") or el.get("type") == "application/ld+json":
            continue
        el.decompose()
    for kommentar in soup.find_all(string=lambda s: isinstance(s, Comment)):
        kommentar.extract()
    return str(soup)


if __name__ == "__main__":
    quelle, ziel = sys.argv[1], sys.argv[2]
    with open(quelle, encoding="utf-8") as f:
        klein = verkleinern(f.read())
    with open(ziel, "w", encoding="utf-8") as f:
        f.write(klein)
    print(f"{ziel}: {len(klein) // 1024} KB")
