"""Gegenprobe mit echten Seiten: Stimmt, was der Bot erkennt?

Läuft auf GitHub (Branch "erkundung") mit dem Bot-Code von main:
1. Alle Set-Suchen und Kategorien wie beim normalen Lauf abrufen.
2. Für jedes Produkt, das laut Liste verfügbar ist (und zum Filter passt), die Produktseite
   öffnen und den Status dort erneut bestimmen – plus einfache Textsignale wie „ausverkauft“.
3. Einige als AUSVERKAUFT erkannte Produkte ebenfalls öffnen (Gegenrichtung).
4. mydealz-Feed roh speichern und lesen.
Abweichungen werden mit Seite gespeichert, alles andere nur im Bericht notiert.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys

HAUPT = pathlib.Path(os.environ["HAUPT"])  # entpackter Code von main
sys.path.insert(0, str(HAUPT))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from bs4 import BeautifulSoup  # noqa: E402

from bot.abruf import Abrufer  # noqa: E402
from bot.adapter import ADAPTER, adapter_fuer  # noqa: E402
from bot.einstellungen import lade_einstellungen  # noqa: E402
from bot.feeds import lies_rss  # noqa: E402
from bot.lauf import MAX_SUCHSEITEN, enthaelt_wort  # noqa: E402
from bot.status import Status  # noqa: E402
from holen import SCHLUESSEL, aufraeumen  # noqa: E402

ZIEL = pathlib.Path("erkundung/ergebnis") / f"pruefung-{datetime.datetime.utcnow():%Y%m%d-%H%M}"
VERFUEGBAR = {Status.BESTELLBAR, Status.VORBESTELLBAR, Status.NUR_EINLADUNG}
MINI_TIN = ["Mini-Tin", "Mini-Tins", "Mini Tin", "Mini Tins"]  # kommt neu in den Filter
MAX_PRODUKTSEITEN = 45       # pro Shop, verfügbare
MAX_AUSVERKAUFT_PROBE = 8    # pro Shop, Gegenrichtung
EXTRA_KATEGORIEN = ["https://games-island.eu/c/Pokemon/Tins"]
FEED = "https://www.mydealz.de/rss/gruppe/pokemon"

SIGNALE = {
    "ausverkauft": re.compile(r"ausverkauft", re.I),
    "nicht_verfuegbar": re.compile(r"nicht (mehr )?verf(ü|ue)gbar|nicht lieferbar|vergriffen", re.I),
    "benachrichtigen": re.compile(r"benachrichtig", re.I),
    "warenkorb": re.compile(r"in den warenkorb", re.I),
    "vorbestellen": re.compile(r"vorbestell", re.I),
    "ribbon_7": re.compile(r"ribbon-7"),
    "status_0": re.compile(r"status-0"),
}


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    e = lade_einstellungen(HAUPT / "config.yaml")
    abrufer = Abrufer(e.allgemein.user_agent, 5, robots_beachten=False,
                      pausen={d: a.min_abstand_sekunden + 5 for a in ADAPTER if a.min_abstand_sekunden
                              for d in a.abruf_domains()})
    nur_mit = list(e.kategorie_filter.nur_mit) + MINI_TIN
    ohne = list(e.kategorie_filter.ohne)

    def passt(titel):
        return any(enthaelt_wort(titel, w) for w in nur_mit) and not any(enthaelt_wort(titel, w) for w in ohne)

    bericht = {"abrufe": [], "listen_produkte": [], "vergleiche": [], "feed": {}, "auffaellig": []}
    produkte: dict[str, dict] = {}

    def hole(url):
        adapter = adapter_fuer(url)
        seite = abrufer.hole(adapter.abruf_url(url) if adapter else url)
        bericht["abrufe"].append({"url": url, "http": seite.http, "problem": seite.problem,
                                  "gesperrt": seite.gesperrt, "laenge": len(seite.text or "")})
        return seite

    def merke(eintrag, shop, quelle):
        t = eintrag.ergebnis
        info = produkte.setdefault(eintrag.url, {
            "url": eintrag.url, "shop": shop, "titel": t.titel, "status": t.status.value, "preis": t.preis,
            "liefertermin": t.liefertermin, "passt": passt(t.titel), "quellen": []})
        if info["status"] != t.status.value:
            bericht["auffaellig"].append({"art": "verschiedener Status in zwei Listen", "url": eintrag.url,
                                          "a": info["status"], "b": t.status.value, "quelle": quelle})
        info["quellen"].append(quelle)

    # 1. Set-Suche (wie im Bot: Begriff muss im Titel stehen)
    for produkt in e.watchlist:
        for adapter in ADAPTER:
            if not adapter.treffer_pro_seite:
                continue
            for begriff in produkt.suche:
                for nummer in range(1, MAX_SUCHSEITEN + 1):
                    url = adapter.such_url(begriff, nummer)
                    seite = hole(url)
                    if seite.text is None:
                        break
                    eintraege = adapter.erkenne_liste(seite.text, url)
                    for x in eintraege:
                        if enthaelt_wort(x.ergebnis.titel, begriff):
                            merke(x, adapter.name, f"suche:{begriff}")
                    if len(eintraege) < adapter.treffer_pro_seite:
                        break

    # 2. Kategorien
    for link in [k.link for k in e.kategorien if "games-island" not in k.link] + EXTRA_KATEGORIEN:
        adapter = adapter_fuer(link)
        seite = hole(link)
        if seite.text is None:
            continue
        eintraege = adapter.erkenne_liste(seite.text, link)
        if not eintraege:
            bericht["auffaellig"].append({"art": "Kategorie ohne Produkte", "url": link})
        for x in eintraege:
            merke(x, adapter.name, f"kategorie:{link}")
        unbekannt = [x.url for x in eintraege if x.ergebnis.status == Status.UNBEKANNT]
        if unbekannt:
            bericht["auffaellig"].append({"art": "UNBEKANNT in Liste", "url": link, "produkte": unbekannt[:20]})

    bericht["listen_produkte"] = sorted(produkte.values(), key=lambda p: (p["shop"], p["titel"] or ""))

    # 3. Produktseiten gegenprüfen (Games Island nicht: dort gibt es nur die Liste für Programme)
    for shop in ("Gate to the Games", "Card-Corner"):
        kandidaten = [p for p in produkte.values() if p["shop"] == shop and p["passt"]]
        verfuegbar = [p for p in kandidaten if Status(p["status"]) in VERFUEGBAR][:MAX_PRODUKTSEITEN]
        ausverkauft = [p for p in kandidaten if p["status"] == "AUSVERKAUFT"][:MAX_AUSVERKAUFT_PROBE]
        for p in verfuegbar + ausverkauft:
            adapter = adapter_fuer(p["url"])
            seite = hole(p["url"])
            if seite.text is None:
                bericht["vergleiche"].append({**p, "seite": None, "problem": seite.problem})
                continue
            ergebnis = adapter.erkenne_produkt(seite.text, p["url"])
            signale = _signale(seite.text)
            vergleich = {"url": p["url"], "shop": shop, "titel": p["titel"], "liste": p["status"],
                         "produktseite": ergebnis.status.value, "preis_liste": p["preis"],
                         "preis_seite": ergebnis.preis, "liefertermin": ergebnis.liefertermin,
                         "mengenlimit": ergebnis.mengenlimit, "hinweis": ergebnis.hinweis, "signale": signale}
            bericht["vergleiche"].append(vergleich)
            gruende = []
            if ergebnis.status.value != p["status"]:
                gruende.append("Liste und Produktseite unterschiedlich")
            if ergebnis.status in VERFUEGBAR and signale.get("ausverkauft_im_produkt"):
                gruende.append("verfügbar erkannt, aber Ausverkauft-Signal auf der Seite")
            if ergebnis.status == Status.AUSVERKAUFT and signale.get("warenkorb_knopf_aktiv"):
                gruende.append("ausverkauft erkannt, aber Warenkorb-Knopf aktiv")
            if ergebnis.status in VERFUEGBAR and not signale.get("warenkorb_knopf_aktiv"):
                gruende.append("verfügbar erkannt, aber kein sichtbarer Warenkorb-Knopf")
            if p["preis"] and ergebnis.preis and abs(p["preis"] - ergebnis.preis) > 0.01:
                gruende.append("Preis in Liste und auf Produktseite unterschiedlich")
            if gruende:
                name = re.sub(r"[^\w]+", "_", p["url"].split("/")[-1])[:60]
                (ZIEL / f"{name}.html").write_text(aufraeumen(seite.text), encoding="utf-8")
                bericht["auffaellig"].append({"art": "; ".join(gruende), **vergleich, "datei": f"{name}.html"})

    # 4. mydealz-Feed (roh speichern – XML nicht „aufräumen“)
    seite = hole(FEED)
    if seite.text:
        (ZIEL / "mydealz_feed.xml").write_text(SCHLUESSEL.sub("[entfernt]", seite.text), encoding="utf-8")
        deals = lies_rss(seite.text)
        bericht["feed"] = {"anzahl": len(deals), "deals": [
            {"titel": d.titel, "haendler": d.haendler, "preis": d.preis, "passt": passt(d.titel),
             "einladung": d.mit_einladung, "guid": d.guid, "link": d.link} for d in deals]}

    (ZIEL / "bericht.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"abrufe": len(bericht["abrufe"]), "produkte": len(produkte),
                      "vergleiche": len(bericht["vergleiche"]), "auffaellig": bericht["auffaellig"]},
                     ensure_ascii=False, indent=1))


def _signale(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    haupt = soup.select_one("#result-wrapper") or soup
    text = " ".join(haupt.get_text(" ").split())
    signale = {name: bool(muster.search(str(haupt) if name in ("ribbon_7", "status_0") else text))
               for name, muster in SIGNALE.items()}
    status_el = haupt.select_one(".delivery-status, .status")
    signale["lieferstatus_text"] = " ".join(status_el.get_text(" ").split())[:120] if status_el else None
    ausverkauft_el = haupt.select_one(".delivery-status")
    signale["ausverkauft_im_produkt"] = bool(ausverkauft_el and re.search("ausverkauft", ausverkauft_el.get_text(), re.I))
    # JTL hat immer einen versteckten Standard-Knopf (btn-hidden) – nur der sichtbare zählt
    knopf = haupt.select_one("button[name=inWarenkorb]:not(.btn-hidden)")
    signale["warenkorb_knopf_aktiv"] = bool(knopf and not knopf.has_attr("disabled"))
    return signale


if __name__ == "__main__":
    main()
