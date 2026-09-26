# 📱 Einrichtung komplett vom iPhone aus

Du brauchst nur **WhatsApp**, die **GitHub-App** und **Safari**. Das dauert ungefähr 5 Minuten.

> 🔒 **Wichtig:** Der CallMeBot-API-Key ist wie ein Passwort. Schick ihn niemandem und
> schreib ihn nie in eine Datei im Repo. Er gehört **nur** in die GitHub Secrets.

---

## Schritt 1: WhatsApp mit CallMeBot verbinden

CallMeBot ist ein kostenloser Dienst, über den der Bot dir WhatsApp-Nachrichten schicken kann.

1. Speichere diese Nummer in deinen iPhone-Kontakten, z. B. unter dem Namen **CallMeBot**:
   **+34 623 78 64 49**

   > Die Nummer kann sich ändern. Die aktuelle steht immer hier:
   > https://www.callmebot.com/blog/free-api-whatsapp-messages/
2. Öffne **WhatsApp** und starte einen Chat mit **CallMeBot**.
   Falls der Kontakt nicht auftaucht, zieh die Chat-Liste einmal nach unten, damit sie sich aktualisiert.
3. Schick genau diesen Text:
   ```
   I allow callmebot to send me messages
   ```
4. Nach kurzer Zeit antwortet CallMeBot ungefähr so:
   *„API Activated for your phone number. Your APIKEY is 123456“*.
   Die Zahl am Ende ist dein **API-Key**. Merk sie dir oder kopier sie.

   > Keine Antwort nach 2 Minuten? Laut CallMeBot sollst du es dann nach 24 Stunden nochmal versuchen.

---

## Schritt 2: Nummer und API-Key bei GitHub speichern (Secrets)

Secrets kann man in der GitHub-App nicht bearbeiten, deshalb nehmen wir hier **Safari**.

1. Öffne diesen Link in Safari (melde dich an, falls gefragt):
   **https://github.com/davidmergili30-blip/Ping-Bot-/settings/secrets/actions/new**

   > Sieht die Seite komisch aus? Tipp in der Adressleiste auf **„aA“** und dann auf
   > **„Desktop-Website anfordern“**.
2. Erstes Secret:
   - **Name:** `WHATSAPP_NUMMER`
   - **Secret:** deine Handynummer **mit Ländervorwahl**, also `+49` statt der ersten `0`.
     Beispiel: Aus `0170 1234567` wird `+491701234567`.
   - Dann auf **Add secret** tippen.
3. Öffne den Link von oben nochmal und leg das zweite Secret an:
   - **Name:** `CALLMEBOT_APIKEY`
   - **Secret:** der API-Key aus Schritt 1 (nur die Zahl)
   - Dann auf **Add secret** tippen.

Die Namen müssen genau so geschrieben sein, mit Großbuchstaben und Unterstrich.

---

## Schritt 3: Test-Nachricht ans iPhone 🎉

1. Öffne die **GitHub-App** und dann dein Repo **Ping-Bot-**.
2. Scroll nach unten und tipp auf **Actions**.
3. Tipp auf den Workflow **Preis-Bot**.
4. Tipp auf **Run workflow**. Je nach App-Version steht das oben rechts oder hinter den drei Punkten **⋯**.
5. Bei „Was soll der Bot tun?“ wählst du **test-nachricht** und tippst auf **Run workflow**.
6. Nach ungefähr 1 Minute bekommst du diese WhatsApp-Nachricht von CallMeBot:

   ```
   ✅ Dein Pokémon-Preis-Bot läuft!
   Test gestartet am 27.09.2026 um 10:15 Uhr.

   Wenn du das liest, ist Phase 1 geschafft. 🎉

   👉 GitHub: https://github.com/davidmergili30-blip/Ping-Bot-/actions
   ```

> Findest du „Run workflow“ in der App nicht? Dann geht es auch in Safari:
> **https://github.com/davidmergili30-blip/Ping-Bot-/actions/workflows/bot.yml**
> Dort tippst du auf **Run workflow**.

---

## Schritt 4: Läuft der Zeitplan?

Unter **Actions** sollten jetzt ungefähr alle 15 Minuten neue Läufe von **Preis-Bot** mit einem
grünen Haken ✅ erscheinen. Bis Phase 2 tun diese Läufe noch nichts Sichtbares.

> ⏱️ GitHub startet geplante Läufe manchmal 5–30 Minuten zu spät, vor allem wenn gerade viel los ist.
> Das ist normal und lässt sich bei der Gratis-Version nicht ändern.

---

## Wenn etwas nicht klappt

Ein **rotes ✗** bei einem Lauf heißt, dass etwas schiefgegangen ist. So findest du den Grund:
Tipp den Lauf an, dann **bot** und dann **Bot starten**. Dort steht auf Deutsch, was fehlt.

| Meldung | Lösung |
|---|---|
| „brauchst du beide Secrets“ | Schritt 2 wiederholen. Hast du die Namen genau so geschrieben? |
| „muss mit Ländervorwahl anfangen“ | Secret `WHATSAPP_NUMMER` ändern: `+49…` statt `0…` |
| „CallMeBot lehnt den API-Key ab“ | Secret `CALLMEBOT_APIKEY` prüfen (nur die Zahl, ohne Leerzeichen) |
| „CallMeBot-Limit erreicht“ | Es wurden mehr als 25 Nachrichten in 4 Stunden geschickt. Einfach warten. |
| „CallMeBot ist gerade nicht erreichbar“ | Der Dienst hat eine Störung. Später nochmal versuchen. |

Ein vorhandenes Secret änderst du über das Stift-Symbol auf dieser Seite:
https://github.com/davidmergili30-blip/Ping-Bot-/settings/secrets/actions

Bei einem roten ✗ schickt GitHub dir außerdem eine E-Mail. Das ist normal.

---

## Gut zu wissen

**Zu CallMeBot:**
- Kostenlos, aber nur für private Nutzung.
- Höchstens **25 Nachrichten in 4 Stunden**. Deshalb fasst der Bot alle Neuigkeiten eines Laufs in **einer** Nachricht zusammen.
- Der Bot kann dir nur **schreiben**. Buttons gibt es nicht, aber Links in der Nachricht kannst du antippen.
- CallMeBot ist ein fremder Dienst. Er sieht die Texte der Pings, also nur Produktinfos und keine Passwörter. Er kann auch mal ausfallen.

**Zur Steuerung:**
- Den Bot steuerst du über die **GitHub-App**, über **Actions → Preis-Bot → Run workflow**. Ab Phase 3 kommen dort weitere Knöpfe dazu, z. B. Watchlist anzeigen, Produkt hinzufügen, Pause oder Scan.
- Nur du kannst diese Knöpfe drücken, weil nur du Schreibrechte am Repo hast. Andere können den Bot also nicht steuern.

**Zum öffentlichen Repo:**
- Jeder kann den **Code**, die **config.yaml** (also deine Watchlist) und die **Protokolle** der Läufe sehen.
- **Secrets sieht niemand**, auch nicht in den Protokollen. Deine Nummer und deinen API-Key schreibt der Bot nie ins Protokoll.
- Wenn im Repo 60 Tage lang nichts passiert, pausiert GitHub den Zeitplan. Du bekommst dann eine E-Mail
  und kannst ihn unter **Actions → Preis-Bot → Enable workflow** mit einem Tipp wieder einschalten.
