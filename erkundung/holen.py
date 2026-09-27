"""Erkundungs-Werkzeug: holt Shop-Seiten höflich ab, damit wir sie untersuchen können.

- prüft vorher die robots.txt (verbotene Seiten werden NICHT abgerufen)
- ehrlicher User-Agent, 5 Sekunden Pause zwischen Anfragen
- speichert die Seiten unter erkundung/ergebnis/ und schreibt eine Übersicht
"""

import json
import pathlib
import re
import time
import urllib.parse
import urllib.robotparser

import requests
from bs4 import BeautifulSoup, Comment

# Zugangsschlüssel, die Shops in ihre Seiten einbauen (z. B. für Karten) – nie ins Repo übernehmen
SCHLUESSEL = re.compile(r"\b(?:pk|sk|tk)\.eyJ[\w.-]+|AIza[0-9A-Za-z_-]{35}|\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")

UA = "PokemonPreisBot/0.1 (privater Preisalarm; +https://github.com/davidmergili30-blip/Ping-Bot-)"
KOPF = {"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"}
PAUSE = 5
ZIEL = pathlib.Path("erkundung/ergebnis") / time.strftime("lauf-%Y%m%d-%H%M")
# Games Island erlaubt höchstens 5 Anfragen in 5 Minuten -> dort 70 Sekunden Pause
PAUSE_SPEZIAL = {"crawlme.games-island.eu": 70}

SOZIAL = re.compile(
    r"https?://(?:www\.)?(?:discord\.gg|discord\.com/invite|whatsapp\.com/channel|chat\.whatsapp\.com|"
    r"wa\.me|t\.me|instagram\.com|tiktok\.com|youtube\.com|facebook\.com|x\.com|twitter\.com)/[^\s\"'<>)]*",
    re.I,
)
SYSTEM = ["shopware", "shopify", "jtl", "woocommerce", "plentymarkets", "gambio", "oxid", "magento",
          "prestashop", "shopify-section", "sw-", "wix", "cloudflare", "__cf_bm", "captcha"]

robots = {}


def robots_fuer(url: str) -> urllib.robotparser.RobotFileParser:
    teile = urllib.parse.urlsplit(url)
    basis = f"{teile.scheme}://{teile.netloc}"
    if basis not in robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(basis + "/robots.txt", headers=KOPF, timeout=20)
            (ZIEL / f"{teile.netloc}_robots.txt").write_text(f"HTTP {r.status_code}\n\n{r.text}", encoding="utf-8")
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True
            elif 400 <= r.status_code < 500:
                rp.allow_all = True
            else:
                rp.disallow_all = True
        except requests.RequestException as f:
            (ZIEL / f"{teile.netloc}_robots.txt").write_text(f"FEHLER {type(f).__name__}", encoding="utf-8")
            rp.disallow_all = True
        robots[basis] = rp
        time.sleep(pause_fuer(url))
    return robots[basis]


def pause_fuer(url: str) -> int:
    return PAUSE_SPEZIAL.get(urllib.parse.urlsplit(url).netloc, PAUSE)


def aufraeumen(html: str) -> str:
    """Skripte, Styles & Co. entfernen (JSON-LD bleibt) und Schlüssel unkenntlich machen."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(["script", "style", "svg", "noscript", "iframe", "img", "picture", "link", "meta"]):
        if el.decomposed or el.get("itemprop") or el.get("type") == "application/ld+json":
            continue
        el.decompose()
    for kommentar in soup.find_all(string=lambda s: isinstance(s, Comment)):
        kommentar.extract()
    return SCHLUESSEL.sub("[entfernt]", str(soup))


def discord_info(link: str) -> dict:
    code = link.rstrip("/").split("/")[-1].split("?")[0]
    try:
        r = requests.get(f"https://discord.com/api/v10/invites/{code}?with_counts=true", headers=KOPF, timeout=20)
        d = r.json()
        return {"code": code, "http": r.status_code, "server": (d.get("guild") or {}).get("name"),
                "mitglieder": d.get("approximate_member_count"), "kanal": (d.get("channel") or {}).get("name")}
    except Exception as f:  # nur Erkundung – Fehler einfach notieren
        return {"code": code, "fehler": type(f).__name__}


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    zeilen = [z.split() for z in pathlib.Path("erkundung/urls.txt").read_text(encoding="utf-8").splitlines()
              if z.strip() and not z.startswith("#")]
    uebersicht = []
    extra_discord = [f"https://discord.gg/{url}" for kuerzel, url in zeilen if kuerzel == "discord"]
    zeilen = [z for z in zeilen if z[0] != "discord"]
    for nr, (kuerzel, url) in enumerate(zeilen, start=1):
        eintrag = {"nr": nr, "kuerzel": kuerzel, "url": url}
        if not robots_fuer(url).can_fetch(UA, url):
            eintrag["ergebnis"] = "VERBOTEN laut robots.txt – nicht abgerufen"
            uebersicht.append(eintrag)
            continue
        try:
            r = requests.get(url, headers=KOPF, timeout=30)
        except requests.RequestException as f:
            eintrag["ergebnis"] = f"FEHLER {type(f).__name__}"
            uebersicht.append(eintrag)
            time.sleep(pause_fuer(url))
            continue
        datei = ZIEL / f"{nr:02d}_{kuerzel}.{'json' if 'json' in r.headers.get('content-type', '') else 'html'}"
        # Kleine Seiten roh speichern (um zu sehen, was da ist), große aufgeräumt
        roh = len(r.text) < 20000
        datei.write_text(SCHLUESSEL.sub("[entfernt]", r.text) if roh else aufraeumen(r.text), encoding="utf-8")
        klein = r.text.lower()
        eintrag.update({
            "http": r.status_code,
            "end_url": r.url,
            "groesse": len(r.text),
            "datei": datei.name,
            "kopfzeilen": {k: v for k, v in r.headers.items()
                           if k.lower() in ("server", "cf-ray", "x-powered-by", "content-type", "x-shopid",
                                            "x-shopify-stage", "powered-by", "x-cache")},
            "system_hinweise": sorted({s for s in SYSTEM if s in klein}),
            "sozial": sorted(set(SOZIAL.findall(r.text))),
            "newsletter_erwaehnt": "newsletter" in klein,
            "pokemon_links": sorted({a for a in re.findall(r'href="([^"]+)"', r.text) if "pokemon" in a.lower()})[:40],
            "roh_gespeichert": roh,
        })
        uebersicht.append(eintrag)
        time.sleep(pause_fuer(url))

    discord_links = sorted({s for e in uebersicht for s in e.get("sozial", []) if "discord" in s.lower()} | set(extra_discord))
    discord = [discord_info(l) for l in discord_links]
    (ZIEL / "uebersicht.json").write_text(
        json.dumps({"seiten": uebersicht, "discord": discord}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"seiten": uebersicht, "discord": discord}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
