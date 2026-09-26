"""Tests für den WhatsApp-Helfer (CallMeBot) – ohne echtes Internet.

Statt wirklich an CallMeBot zu senden, ersetzen wir requests.get durch
eine Attrappe, die sich merkt, was geschickt wurde.
"""

import pytest
import requests

from bot import whatsapp as whatsapp_modul
from bot.whatsapp import WhatsApp, WhatsAppFehler, pruefe_nummer

ERFOLG = "<html><body><p><b>Message queued</b>. You will receive it in a few seconds.</p></body></html>"
LIMIT = ("There is currently a limit of 25 messages per 240 minutes. Please try to reduce "
         "the number of messages sent. For example, group them into one message.")


class FalscheAntwort:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


@pytest.fixture
def callmebot(monkeypatch):
    """Ersetzt CallMeBot. callmebot['antwort'] = was zurückkommen soll."""
    attrappe = {"antwort": FalscheAntwort(ERFOLG), "gesendet": []}

    def falsches_get(url, params, timeout):
        attrappe["gesendet"].append({"url": url, "params": params})
        return attrappe["antwort"]

    monkeypatch.setattr(whatsapp_modul.requests, "get", falsches_get)
    return attrappe


def test_nachricht_wird_gesendet(callmebot):
    WhatsApp("+49 170 1234567", "123456").sende("Hallo *Welt*")
    anfrage = callmebot["gesendet"][0]
    assert anfrage["url"] == "https://api.callmebot.com/whatsapp.php"
    assert anfrage["params"] == {"phone": "+491701234567", "text": "Hallo *Welt*", "apikey": "123456"}


def test_limit_wird_erkannt_obwohl_http_200(callmebot):
    callmebot["antwort"] = FalscheAntwort(LIMIT)
    with pytest.raises(WhatsAppFehler, match="25 Nachrichten"):
        WhatsApp("+491701234567", "123456").sende("Hallo")


def test_falscher_api_key(callmebot):
    callmebot["antwort"] = FalscheAntwort("APIKey is invalid. You need to get a new one.")
    with pytest.raises(WhatsAppFehler, match="CALLMEBOT_APIKEY"):
        WhatsApp("+491701234567", "123456").sende("Hallo")


def test_unbekannte_antwort_ist_ein_fehler(callmebot):
    # Lieber ein Fehler zu viel als ein verschluckter Ping
    callmebot["antwort"] = FalscheAntwort("Something unexpected")
    with pytest.raises(WhatsAppFehler, match="nicht angenommen"):
        WhatsApp("+491701234567", "123456").sende("Hallo")


def test_http_fehler(callmebot):
    callmebot["antwort"] = FalscheAntwort("Message queued", status_code=500)
    with pytest.raises(WhatsAppFehler, match="HTTP 500"):
        WhatsApp("+491701234567", "123456").sende("Hallo")


def test_geheimnisse_werden_in_antwort_geschwaerzt(callmebot):
    callmebot["antwort"] = FalscheAntwort("Error for phone +491701234567 with key 987654")
    with pytest.raises(WhatsAppFehler) as info:
        WhatsApp("+491701234567", "987654").sende("Hallo")
    assert "491701234567" not in str(info.value)
    assert "987654" not in str(info.value)


def test_geheimnisse_nie_in_verbindungsfehler(monkeypatch):
    def kaputt(url, params, timeout):
        # Echte requests-Fehler enthalten die komplette Adresse – mit Key und Nummer
        raise requests.ConnectionError(f"Verbindung zu {url}?apikey={params['apikey']} fehlgeschlagen")

    monkeypatch.setattr(whatsapp_modul.requests, "get", kaputt)
    with pytest.raises(WhatsAppFehler) as info:
        WhatsApp("+491701234567", "GEHEIM").sende("Hallo")
    assert "GEHEIM" not in str(info.value)
    assert info.value.__suppress_context__


def test_ohne_secrets_klare_meldung():
    with pytest.raises(WhatsAppFehler, match="WHATSAPP_NUMMER"):
        WhatsApp("", "123456")


@pytest.mark.parametrize(
    "eingabe, erwartet",
    [
        ("+491701234567", "+491701234567"),
        ("+49 170 1234567", "+491701234567"),
        ("0049 170-1234567", "+491701234567"),
        ("+43 (660) 123 4567", "+436601234567"),
    ],
)
def test_nummer_wird_vereinheitlicht(eingabe, erwartet):
    assert pruefe_nummer(eingabe) == erwartet


@pytest.mark.parametrize("eingabe", ["0170 1234567", "+49", "hallo"])
def test_nummer_ohne_laendervorwahl_wird_abgelehnt(eingabe):
    with pytest.raises(WhatsAppFehler, match="Ländervorwahl"):
        pruefe_nummer(eingabe)
