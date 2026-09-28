# 🃏 Pokémon-TCG Preis- & Restock-Bot

Ein privater Bot, der Online-Shops auf versiegelte Pokémon-TCG-Produkte prüft. Dazu gehören Displays,
Elite-/Top-Trainer-Boxen, Premium-Kollektionen und Special Sets auf Deutsch, Englisch und Japanisch.
Sobald etwas nach deinen Regeln interessant ist, schickt er dir eine Nachricht in deinen **Discord**-Kanal.
Der Bot läuft kostenlos über **GitHub Actions** und lässt sich komplett vom **iPhone** aus bedienen.

➡️ **Einrichtung:** [ANLEITUNG_IPHONE.md](ANLEITUNG_IPHONE.md)

## Was der Bot niemals tut

- ❌ Kein automatisches Bestellen, kein Einloggen in Shop-Konten, keine Warenkörbe
- ❌ Keine Captcha- oder Bot-Schutz-Umgehung, keine Proxies, kein Vortäuschen eines Browsers
- ❌ Amazon wird nicht gescrapt, nur über erlaubte Schnittstellen abgefragt
- ✅ Höfliche Abfragen mit ehrlichem User-Agent, jeder Shop höchstens alle 10–30 Minuten
- ℹ️ Die robots.txt der Shops wird auf deinen Wunsch **nicht** beachtet (`robots_txt_beachten: false` in
  config.yaml). Blockt ein Shop trotzdem (403, Captcha, Sperrseite), wird das **nie** umgangen.
- ✅ Wenn eine Seite blockt, heißt der Status `UNBEKANNT`. Die Sperre wird nicht umgangen.
- ✅ Der Discord-Webhook-Link steht nur in den GitHub Secrets, nie im Code

## Status eines Produkts

| Status | Bedeutung |
|---|---|
| `BESTELLBAR` | Auf Lager, direkt kaufbar, Verkauf durch den Shop selbst |
| `VORBESTELLBAR` | Vorbestellung möglich (mit Liefertermin) |
| `NUR_EINLADUNG` | Nur „auf Einladung anfordern“ (z. B. Amazon) |
| `NUR_MARKTPLATZ` | Nur über Drittanbieter oder Marktplatz-Händler |
| `NUR_FILIALE` | Nur im Laden oder zur Abholung |
| `BALD` | „Bald verfügbar“ / „Benachrichtigen“ |
| `AUSVERKAUFT` | Nicht verfügbar |
| `UNBEKANNT` | Nicht sicher erkannt oder die Seite blockt |

## Was der Bot gerade kann (Stand Phase 2)

Der Bot prüft automatisch (geplant alle 15 Minuten – GitHub startet ihn zurzeit aber oft nur alle paar
Stunden, ein bekanntes GitHub-Problem). Per **Run workflow** kannst du jederzeit sofort prüfen lassen:

1. **Deine Watchlist:** ganze Sets per Suchbegriff (z. B. „Dunkelnacht“, „Pitch Black“) oder einzelne
   Produkte per Link. Du bekommst einen Ping, sobald etwas verfügbar wird (z. B. `AUSVERKAUFT → BESTELLBAR`)
   oder ein neues Produkt des Sets auftaucht. Optional: Maximalpreis und Preissturz-Ping.
2. **Kategorien:** z. B. „Vorverkauf“ oder „Neu eingetroffen“. Hier meldet der Bot **neue Produkte und
   Vorbestellungen**, auch wenn sie nicht auf deiner Watchlist stehen. Ein Filter sorgt dafür, dass nur
   Displays, Trainer-Boxen, Booster Bundles, Kollektionen und Mini-Tins gemeldet werden.
3. **Deal-Feed von mydealz:** Dort posten Leute Angebote, sobald sie irgendwo auftauchen – auch bei
   Shops, die der Bot selbst nicht abfragen kann (Amazon, Netto, MediaMarkt, Kaufland …). Neue Deals,
   die zum Filter passen, kommen als 📰-Kasten. Liegt ein Deal über dem Maximalpreis seines Sets, kommt
   kein Ping.

Die Neuigkeiten eines Laufs kommen gebündelt, getrennt nach Art: 🛒 **Jetzt kaufbar**, 🟡 **Nur auf Einladung** und ℹ️ **Übersicht & Hinweise** – jede Art als eigene Discord-Nachricht.

| Shop | Status |
|---|---|
| Shop / Quelle | Status |
|---|---|
| Gate to the Games | ✅ Set-Suche + Kategorie „Vorverkauf“ |
| Card-Corner | ✅ Set-Suche + Kategorie „Neu eingetroffen“ |
| Games Island | ✅ über ihre offizielle Datenliste für Programme (crawlme.games-island.eu): Displays, Top-Trainer-Boxen, Kollektionen. Höchstens 5 Anfragen in 5 Minuten, keine Preise (Wunsch von Games Island) → im Ping steht „Preis im Shop“ |
| mydealz (Pokémon-Gruppe) | ✅ RSS-Feed – deckt indirekt Amazon, Netto, MediaMarkt, Kaufland, Galaxus usw. ab |
| Pokémon Center | 🚫 Bot-Schutz (Incapsula) |
| Kaufland, Thalia, MediaMarkt/Saturn | 🚫 Bot-Schutz (Cloudflare, HTTP 403) → Deals kommen über mydealz |
| Rossmann | 🚫 Bot-Schutz („Client Challenge“) |
| Smyths Toys | 🚫 blockt automatische Abfragen (HTTP 403) |
| Netto | 🚫 blockt automatische Abfragen (Access Denied) → Deals kommen über mydealz |
| Amazon | 🚫 wird nicht gescrapt (Nutzungsbedingungen) → Deals und Einladungen kommen über mydealz |
| Müller | ➖ verkauft online keine versiegelten Pokémon-Produkte (nur Zubehör) – Tipp: Müller-WhatsApp-Kanal |

*Stand der Prüfung: 27.09.2026. Gesperrte Shops werden nicht abgefragt – Sperren werden nie umgangen.*

## Bedienung (GitHub-App)

**Actions → Preis-Bot → Run workflow**, Aktion auswählen, ggf. Felder ausfüllen, **Run workflow**.
Die Antwort kommt in deinen Discord-Kanal.

| Aktion | Felder | Was passiert |
|---|---|---|
| `normaler-lauf` | – | Prüft sofort alle Sets und Kategorien |
| `status` | – | Letzter Lauf, blockierte Shops, was gerade verfügbar ist |
| `watchlist` | – | Zeigt deine Sets mit Suchbegriffen und Maximalpreisen |
| `set-hinzufuegen` | **name**, optional **suchbegriffe** | Neues Set beobachten, z. B. name `Stellarkrone`, suchbegriffe `Stellar Crown` |
| `set-entfernen` | **name** | Set nicht mehr beobachten |
| `max-preis` | **name**, **preis** | Maximalpreis für ein Set, z. B. `180` – mit `aus` wieder aufheben |
| `pause` / `weiter` | – | Alle Prüfungen und Pings anhalten / wieder starten |
| `test-nachricht` | – | Test-Nachricht in deinen Discord-Kanal |

Geänderte Einstellungen speichert der Bot selbst in der [config.yaml](config.yaml). Du kannst die Datei
aber auch weiterhin von Hand bearbeiten ([Anleitung](ANLEITUNG_IPHONE.md#watchlist-bearbeiten)).

## Projektstruktur

```
Ping-Bot-/
├── config.yaml              ← deine Einstellungen (Regeln, Shops, Watchlist)
├── bot/
│   ├── __main__.py          ← Startpunkt: python -m bot <aktion>
│   ├── steuerung.py         ← Knöpfe in der GitHub-App: Sets, Maximalpreise, Pause
│   ├── lauf.py              ← der normale Lauf: prüfen, vergleichen, melden
│   ├── abruf.py             ← lädt Seiten höflich (Pausen, Sperren erkennen, robots.txt abschaltbar)
│   ├── feeds.py             ← liest Deal-Feeds (RSS), z. B. mydealz
│   ├── adapter/             ← ein „Übersetzer“ pro Shop-System
│   │   ├── basis.py         ← gemeinsame Bausteine (Preis, Datum, schema.org)
│   │   ├── jtl.py           ← JTL-Shops: Gate to the Games, Card-Corner
│   │   └── games_island.py  ← Games Island (über crawlme.games-island.eu)
│   ├── pings.py             ← wann gepingt wird und wie der Ping aussieht
│   ├── produkte.py          ← Art, Set und Sprache aus dem Produktnamen (für Preise & Vergleich)
│   ├── speicher.py          ← SQLite-Datenbank (Preis- und Statusverlauf)
│   ├── einstellungen.py     ← liest und prüft config.yaml
│   ├── discord.py           ← schickt Nachrichten über einen Discord-Webhook
│   └── status.py            ← die 8 möglichen Status
├── tests/                   ← automatische Tests
│   └── beispiele/           ← echte, gespeicherte Shop-Seiten für die Tests
├── .github/workflows/
│   ├── bot.yml              ← Zeitplan und Knopf zum Starten
│   └── tests.yml            ← führt bei jeder Änderung die Tests aus
├── requirements.txt         ← benötigte Python-Pakete
└── ANLEITUNG_IPHONE.md      ← Einrichtung Schritt für Schritt
```

## Fortschritt

- [x] **Phase 1:** Grundgerüst, config.yaml, Discord-Test, GitHub Actions
- [x] **Phase 2:** Gate to the Games + Card-Corner, Status-Erkennung, SQLite, Ping nur bei Änderung,
      neue Vorbestellungen in Kategorien, Sets per Suchbegriff
- [x] **Phase 3:** Steuerung über die GitHub-App (Status, Watchlist, Sets, Maximalpreise, Pause)
- [ ] **Phase 4:** Mehr Quellen, Whitelist, Fake-Warnung – *begonnen: Games Island, mydealz-Feed*
- [x] Maximalpreise je Set und Produktart, Preisvergleich zwischen Shops, neue Sets erkennen
- [ ] **Phase 5:** Amazon und Einladungen
- [ ] **Phase 6:** Regeln, Ruhezeiten, Marge
- [ ] **Phase 7:** Neuheiten-Suche
- [ ] **Phase 8:** Deep-Scan

## Neuen Shop einbauen (für später)

1. Beispielseiten holen: Auf dem Branch `erkundung` die Datei `erkundung/urls.txt` anpassen.
   GitHub ruft die Seiten dann höflich ab (mit Pausen) und speichert sie.
2. Seiten mit `tests/beispiele/verkleinern.py` verkleinern und nach `tests/beispiele/` legen.
3. Adapter schreiben (oder `JtlShop` wiederverwenden) und in `bot/adapter/__init__.py` eintragen.

## Tests (für später, am Computer)

```bash
pip install -r requirements.txt
python -m pytest -v
```
