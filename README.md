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
   Displays, Trainer-Boxen, Kollektionen usw. gemeldet werden.

Alle Neuigkeiten eines Laufs kommen gebündelt in **einer** Discord-Nachricht.

| Shop | Status |
|---|---|
| Gate to the Games | ✅ wird geprüft (robots.txt erlaubt es) |
| Card-Corner | ✅ wird geprüft (robots.txt erlaubt es) |
| Games Island | 🚫 verbietet automatisches Abfragen → ihr Discord „Games Island Hof“ nutzen |

## Bedienung

In der GitHub-App: **Actions → Preis-Bot → Run workflow**. Dort wählst du eine Aktion:

| Aktion | Was passiert |
|---|---|
| `normaler-lauf` | Prüft sofort alle Sets und Kategorien. Startet außerdem automatisch (siehe oben). |
| `test-nachricht` | Schickt eine Test-Nachricht in deinen Discord-Kanal |

Watchlist, Kategorien und Regeln änderst du in der [config.yaml](config.yaml). Wie das vom iPhone aus
geht, steht in der [Anleitung](ANLEITUNG_IPHONE.md#watchlist-bearbeiten). Weitere Knöpfe wie Watchlist
anzeigen, Produkt hinzufügen, Pause oder Scan kommen in Phase 3.

## Projektstruktur

```
Ping-Bot-/
├── config.yaml              ← deine Einstellungen (Regeln, Shops, Watchlist)
├── bot/
│   ├── __main__.py          ← Startpunkt: python -m bot <aktion>
│   ├── lauf.py              ← der normale Lauf: prüfen, vergleichen, melden
│   ├── abruf.py             ← lädt Seiten höflich (robots.txt, Pausen, Sperren erkennen)
│   ├── adapter/             ← ein „Übersetzer“ pro Shop-System
│   │   ├── basis.py         ← gemeinsame Bausteine (Preis, Datum, schema.org)
│   │   └── jtl.py           ← JTL-Shops: Gate to the Games, Card-Corner
│   ├── pings.py             ← wann gepingt wird und wie der Ping aussieht
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
      neue Vorbestellungen in Kategorien
- [ ] **Phase 3:** Steuerung über die GitHub-App (Watchlist, Pause, Ruhezeit, Status)
- [ ] **Phase 4:** Mehr Quellen, Whitelist, Fake-Warnung
- [ ] **Phase 5:** Amazon und Einladungen
- [ ] **Phase 6:** Regeln, Ruhezeiten, Marge
- [ ] **Phase 7:** Neuheiten-Suche
- [ ] **Phase 8:** Deep-Scan

## Neuen Shop einbauen (für später)

1. Beispielseiten holen: Auf dem Branch `erkundung` die Datei `erkundung/urls.txt` anpassen.
   GitHub ruft die Seiten dann höflich ab (mit robots.txt-Prüfung) und speichert sie.
2. Seiten mit `tests/beispiele/verkleinern.py` verkleinern und nach `tests/beispiele/` legen.
3. Adapter schreiben (oder `JtlShop` wiederverwenden) und in `bot/adapter/__init__.py` eintragen.

## Tests (für später, am Computer)

```bash
pip install -r requirements.txt
python -m pytest -v
```
