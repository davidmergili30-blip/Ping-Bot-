# 🃏 Pokémon-TCG Preis- & Restock-Bot

Ein privater Bot, der Online-Shops auf versiegelte Pokémon-TCG-Produkte prüft. Dazu gehören Displays,
Elite-/Top-Trainer-Boxen, Premium-Kollektionen und Special Sets auf Deutsch, Englisch und Japanisch.
Sobald etwas nach deinen Regeln interessant ist, schickt er dir eine **WhatsApp-Nachricht** (über CallMeBot).
Der Bot läuft kostenlos über **GitHub Actions** und lässt sich komplett vom **iPhone** aus bedienen.

➡️ **Einrichtung:** [ANLEITUNG_IPHONE.md](ANLEITUNG_IPHONE.md)

## Was der Bot niemals tut

- ❌ Kein automatisches Bestellen, kein Einloggen in Shop-Konten, keine Warenkörbe
- ❌ Keine Captcha- oder Bot-Schutz-Umgehung, keine Proxies, kein Vortäuschen eines Browsers
- ❌ Amazon wird nicht gescrapt, nur über erlaubte Schnittstellen abgefragt
- ✅ Höfliche Abfragen mit ehrlichem User-Agent, jeder Shop höchstens alle 10–30 Minuten
- ✅ Wenn eine Seite blockt, heißt der Status `UNBEKANNT`. Die Sperre wird nicht umgangen.
- ✅ Nummer und API-Key stehen nur in den GitHub Secrets, nie im Code

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

## Bedienung (Stand Phase 1)

In der GitHub-App: **Actions → Preis-Bot → Run workflow**. Dort wählst du eine Aktion:

| Aktion | Was passiert |
|---|---|
| `normaler-lauf` | Der normale Lauf. Er startet automatisch alle 15 Minuten. |
| `test-nachricht` | Schickt eine Test-Nachricht per WhatsApp an dein iPhone |

Weitere Knöpfe wie Watchlist anzeigen, Produkt hinzufügen, Pause oder Scan kommen in Phase 3.

## Projektstruktur

```
Ping-Bot-/
├── config.yaml              ← deine Einstellungen (Regeln, Shops, Watchlist)
├── bot/
│   ├── __main__.py          ← Startpunkt: python -m bot <aktion>
│   ├── einstellungen.py     ← liest und prüft config.yaml
│   ├── whatsapp.py          ← schickt WhatsApp-Nachrichten über CallMeBot
│   └── status.py            ← die 8 möglichen Status
├── tests/                   ← automatische Tests
├── .github/workflows/
│   ├── bot.yml              ← Zeitplan (alle 15 Min.) und Knopf zum Starten
│   └── tests.yml            ← führt bei jeder Änderung die Tests aus
├── requirements.txt         ← benötigte Python-Pakete
└── ANLEITUNG_IPHONE.md      ← Einrichtung Schritt für Schritt
```

## Fortschritt

- [x] **Phase 1:** Grundgerüst, config.yaml, WhatsApp-Test, GitHub Actions
- [ ] **Phase 2:** Erster Shop, Status-Erkennung, SQLite, Ping nur bei Änderung
- [ ] **Phase 3:** Steuerung über die GitHub-App (Watchlist, Pause, Ruhezeit, Status)
- [ ] **Phase 4:** Mehr Quellen, Whitelist, Fake-Warnung
- [ ] **Phase 5:** Amazon und Einladungen
- [ ] **Phase 6:** Regeln, Ruhezeiten, Marge
- [ ] **Phase 7:** Neuheiten-Suche
- [ ] **Phase 8:** Deep-Scan

## Tests (für später, am Computer)

```bash
pip install -r requirements.txt
python -m pytest -v
```
