# 📱 Einrichtung komplett vom iPhone aus

Du brauchst nur **Discord**, die **GitHub-App** und **Safari**. Das dauert ungefähr 10 Minuten.

> 🔒 **Wichtig:** Der Webhook-Link (Schritt 2) ist wie ein Passwort. Wer ihn kennt, kann in deinen
> Kanal schreiben. Schick ihn niemandem und schreib ihn nie in eine Datei im Repo.
> Er gehört **nur** in die GitHub Secrets.

---

## Schritt 1: Eigenen Discord-Server anlegen

1. Installiere **Discord** aus dem App Store und melde dich an (oder registriere dich).
2. Tipp in der Server-Leiste links auf **„+“** (Server hinzufügen) und dann auf **„Eigenen erstellen“**
   und **„Für mich und meine Freunde“**.
3. Gib dem Server einen Namen, z. B. `Pokémon-Alarm`, und tipp auf **Server erstellen**.
4. Leg zwei Textkanäle an. Tipp dazu neben **Textkanäle** auf **„+“**:
   - `preis-pings` → hier schreibt dein Bot hinein
   - `shop-news` → hier landen später die Ankündigungen der Shops (Schritt 6)

Den Server siehst nur du, solange du niemanden einlädst.

---

## Schritt 2: Webhook anlegen (der Link, über den der Bot schreibt)

1. Tipp oben auf den **Servernamen** und dann auf **Einstellungen** (Zahnrad).
2. Tipp auf **Integrationen** → **Webhooks** → **Neuer Webhook** (oder „Webhook erstellen“).
3. Tipp den neuen Webhook an:
   - **Name:** z. B. `Preis-Bot`
   - **Kanal:** `preis-pings`
   - Speichern
4. Tipp auf **Webhook-URL kopieren**. Der Link beginnt mit `https://discord.com/api/webhooks/…`

> Findest du das in der App nicht? Dann öffne in Safari **https://discord.com/app**, tipp in der
> Adressleiste auf **„aA“** und dann auf **„Desktop-Website anfordern“**. Dort findest du denselben Weg über die Server-Einstellungen.

---

## Schritt 3: Webhook bei GitHub speichern (Secret)

Secrets kann man in der GitHub-App nicht bearbeiten, deshalb nehmen wir hier **Safari**.

1. Öffne diesen Link in Safari (melde dich an, falls gefragt):
   **https://github.com/davidmergili30-blip/Ping-Bot-/settings/secrets/actions/new**

   > Sieht die Seite komisch aus? Tipp in der Adressleiste auf **„aA“** und dann auf
   > **„Desktop-Website anfordern“**.
2. **Name:** `DISCORD_WEBHOOK_URL` (genau so, mit Großbuchstaben und Unterstrichen)
3. **Secret:** Halte den Finger lange gedrückt, tipp auf **Einsetzen** und füg den Webhook-Link ein.
4. Tipp auf **Add secret**.

> Hattest du vorher schon `WHATSAPP_NUMMER` oder `CALLMEBOT_APIKEY` angelegt? Die brauchst du nicht mehr.
> Du kannst sie auf https://github.com/davidmergili30-blip/Ping-Bot-/settings/secrets/actions über das
> Mülleimer-Symbol löschen.

---

## Schritt 4: Test-Nachricht 🎉

1. Öffne die **GitHub-App** und dann dein Repo **Ping-Bot-**.
2. Scroll nach unten und tipp auf **Actions** → **Preis-Bot**.
3. Tipp auf **Run workflow**. Je nach App-Version steht das oben rechts oder hinter den drei Punkten **⋯**.
4. Wähl **test-nachricht** und tipp auf **Run workflow**.
5. Nach ungefähr 1 Minute erscheint im Kanal `preis-pings` ein grüner Kasten
   **„✅ Dein Pokémon-Preis-Bot läuft!“**.

> Findest du „Run workflow“ in der App nicht? Dann geht es auch in Safari:
> **https://github.com/davidmergili30-blip/Ping-Bot-/actions/workflows/bot.yml**

---

## Schritt 5: Mitteilungen aufs iPhone

Damit dein iPhone bei jedem Ping Bescheid gibt:

1. **In Discord:** Tipp auf den Servernamen → **Benachrichtigungen** → **Alle Nachrichten**.
2. **Im iPhone:** Öffne **Einstellungen** → **Mitteilungen** → **Discord** → **Mitteilungen erlauben**.

---

## Schritt 6: Ankündigungen der Shops

Viele Shops kündigen Vorbestellungen zuerst auf Discord an. Tritt diesen Servern bei:

| Shop | Discord |
|---|---|
| **Card-Corner** | https://discord.gg/card-corner („Card-Corner TCG Discord“, ca. 10.400 Mitglieder) |
| **Games Island** | https://discord.gg/rvBZKKqqU9 („Games Island Hof“, ca. 3.200 Mitglieder) |
| **Gate to the Games** | kein Discord gefunden. Folge ihnen stattdessen auf Instagram (**@gatetothegames**) oder abonniere den Newsletter auf gate-to-the-games.de |

**Ankündigungen in deinen eigenen Server holen (empfohlen):**
1. Öffne im Shop-Server den **Ankündigungskanal**. Du erkennst ihn am Megafon-Symbol 📢.
2. Tipp oben auf **„Folgen“**. Wähl deinen Server **Pokémon-Alarm** und den Kanal `shop-news`.
3. Ab jetzt landen neue Ankündigungen automatisch in deinem Kanal `shop-news`.

> Gibt es keinen „Folgen“-Knopf? Dann halt den Kanal lange gedrückt → **Benachrichtigungen** →
> **Alle Nachrichten**. So meldet dein iPhone neue Posts direkt aus dem Shop-Server.

---

## Schritt 7: Läuft der Zeitplan?

Unter **Actions** erscheinen automatisch Läufe von **Preis-Bot** mit dem Hinweis **„Scheduled“**.

> ⏱️ Geplant ist alle 15 Minuten. GitHub startet geplante Läufe zurzeit aber oft nur alle paar Stunden
> (bekanntes Problem bei GitHub, nicht bei deinem Bot). Wenn du sofort wissen willst, was los ist:
> **Actions → Preis-Bot → Run workflow → normaler-lauf**.

---

## Watchlist bearbeiten

Alle Einstellungen stehen in der Datei **config.yaml**. So änderst du sie vom iPhone aus:

1. Öffne in Safari: **https://github.com/davidmergili30-blip/Ping-Bot-/edit/main/config.yaml**
   (falls nötig: **„aA“** → **„Desktop-Website anfordern“**)
2. Scroll zu **watchlist:**. Es gibt zwei Arten von Einträgen. Achte genau auf die Leerzeichen am Zeilenanfang.

   **Ein ganzes Set beobachten (empfohlen):** Der Bot sucht in den Shops nach dem Namen und beobachtet
   alle Displays, Trainer-Boxen, Bundles und Kollektionen dieses Sets. Trag am besten den deutschen,
   englischen und japanischen Namen ein:
   ```yaml
     - name: "Dunkelnacht"
       suche:
         - Dunkelnacht
         - Pitch Black
   ```

   **Ein einzelnes Produkt per Link:**
   ```yaml
     - name: "Mein Produkt (DE)"
       links:
         - https://www.gate-to-the-games.de/...
       max_preis: 180
   ```
   Den Link bekommst du, indem du das Produkt im Shop öffnest und die Adresse kopierst
   (Teilen-Symbol → **Kopieren**). `max_preis` ist optional.
3. Tipp oben rechts auf **Commit changes…** und dann nochmal auf **Commit changes**.
4. Ab dem nächsten Lauf gilt die neue Watchlist.

> Hast du dich vertippt? Kein Problem: Beim nächsten Lauf gibt es ein rotes ✗, und im Protokoll steht
> auf Deutsch, in welcher Zeile der Fehler ist.

**Kategorien** (weiter unten in derselben Datei) sind Shop-Seiten wie „Vorverkauf“ oder „Neu eingetroffen“.
Dort meldet der Bot neue Produkte und Vorbestellungen, auch wenn sie nicht auf deiner Watchlist stehen.
Beim ersten Mal bekommst du eine **Übersicht** („📋 Neu überwacht …“), danach nur noch Neuigkeiten.
Mit **kategorie_filter** legst du fest, welche Produkte dich interessieren (z. B. nur Displays und Trainer-Boxen).
Der Filter gilt für die Kategorien und für die Set-Suche.

Auch bei jedem **neuen Set** auf der Watchlist bekommst du beim ersten Mal eine Übersicht pro Shop
(„📋 Neu überwacht: Dunkelnacht bei Card-Corner“). Danach meldet der Bot nur noch, wenn ein Produkt
**wieder verfügbar** wird oder **neu** dazukommt.

---

## Wenn etwas nicht klappt

Ein **rotes ✗** bei einem Lauf heißt, dass etwas schiefgegangen ist. So findest du den Grund:
Tipp den Lauf an, dann **bot** und dann **Bot starten**. Dort steht auf Deutsch, was fehlt.

| Meldung | Lösung |
|---|---|
| „brauchst du das Secret DISCORD_WEBHOOK_URL“ | Schritt 3 wiederholen. Ist der Name genau richtig geschrieben? |
| „sieht nicht wie ein Discord-Webhook aus“ | Du hast etwas anderes kopiert. Kopier den Link nochmal wie in Schritt 2. |
| „Webhook-Link ist ungültig oder wurde gelöscht“ | Leg einen neuen Webhook an (Schritt 2) und ändere das Secret über das Stift-Symbol auf https://github.com/davidmergili30-blip/Ping-Bot-/settings/secrets/actions |
| „Discord ist gerade nicht erreichbar“ | Discord hat eine Störung. Beim nächsten Lauf klappt es meistens wieder. Es geht kein Ping verloren. |
| „Fehler in config.yaml“ | Du hast dich beim Bearbeiten vertippt. Die Meldung sagt, wo. |

Bei einem roten ✗ schickt GitHub dir außerdem eine E-Mail. Das ist normal.

---

## Gut zu wissen

**Zur Steuerung:**
- Den Bot steuerst du über die **GitHub-App**, über **Actions → Preis-Bot → Run workflow**. Ab Phase 3 kommen weitere Knöpfe dazu.
- Nur du kannst diese Knöpfe drücken, weil nur du Schreibrechte am Repo hast.

**Zum öffentlichen Repo:**
- Jeder kann den **Code**, die **config.yaml** (also deine Watchlist) und die **Protokolle** der Läufe sehen.
- **Secrets sieht niemand**, auch nicht in den Protokollen. Der Bot schreibt den Webhook-Link nie ins Protokoll.
- Wenn im Repo 60 Tage lang nichts passiert, pausiert GitHub den Zeitplan. Du bekommst dann eine E-Mail
  und kannst ihn unter **Actions → Preis-Bot → Enable workflow** mit einem Tipp wieder einschalten.
