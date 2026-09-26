"""Tests für den Discord-Versand – ohne echtes Internet.

Statt wirklich an Discord zu senden, ersetzen wir requests.post durch
eine Attrappe, die sich merkt, was geschickt wurde.
"""

import pytest
import requests

from bot import discord as discord_modul
from bot.discord import DiscordFehler, DiscordWebhook, Kasten

WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/GEHEIMER_teil-xyz"


class FalscheAntwort:
    def __init__(self, status_code=200, inhalt=None):
        self.status_code = status_code
        self._inhalt = inhalt or {}

    def json(self):
        return self._inhalt


@pytest.fixture
def discord(monkeypatch):
    """Ersetzt Discord. discord['antworten'] = Antworten der Reihe nach (sonst 200)."""
    attrappe = {"antworten": [], "gesendet": []}

    def falsches_post(url, json, params, timeout):
        attrappe["gesendet"].append({"url": url, "daten": json, "params": params})
        return attrappe["antworten"].pop(0) if attrappe["antworten"] else FalscheAntwort()

    monkeypatch.setattr(discord_modul.requests, "post", falsches_post)
    return attrappe


def test_nachricht_mit_kasten(discord):
    DiscordWebhook(WEBHOOK).sende(
        text="Hallo",
        kaesten=[Kasten(titel="🟢 BESTELLBAR – Display", text="144,99 €", link="https://shop.de/x", farbe=0x2ECC71)],
    )
    anfrage = discord["gesendet"][0]
    assert anfrage["url"] == WEBHOOK
    assert anfrage["params"] == {"wait": "true"}
    assert anfrage["daten"]["content"] == "Hallo"
    assert anfrage["daten"]["allowed_mentions"] == {"parse": []}
    assert anfrage["daten"]["embeds"] == [
        {"title": "🟢 BESTELLBAR – Display", "description": "144,99 €", "url": "https://shop.de/x", "color": 0x2ECC71}
    ]


def test_viele_kaesten_werden_aufgeteilt(discord):
    kaesten = [Kasten(titel=f"Produkt {i}") for i in range(23)]
    DiscordWebhook(WEBHOOK).sende(kaesten=kaesten)
    assert [len(a["daten"]["embeds"]) for a in discord["gesendet"]] == [10, 10, 3]


def test_lange_kaesten_werden_nach_zeichen_aufgeteilt(discord):
    kaesten = [Kasten(titel="X", text="a" * 3000) for _ in range(3)]
    DiscordWebhook(WEBHOOK).sende(kaesten=kaesten)
    assert [len(a["daten"]["embeds"]) for a in discord["gesendet"]] == [1, 1, 1]


def test_ungueltiger_webhook(discord):
    discord["antworten"] = [FalscheAntwort(404, {"message": "Unknown Webhook", "code": 10015})]
    with pytest.raises(DiscordFehler, match="DISCORD_WEBHOOK_URL"):
        DiscordWebhook(WEBHOOK).sende(text="Hallo")


def test_bei_429_wird_einmal_gewartet_und_wiederholt(discord):
    discord["antworten"] = [FalscheAntwort(429, {"retry_after": 1.5})]
    gewartet = []
    DiscordWebhook(WEBHOOK, schlafen=gewartet.append).sende(text="Hallo")
    assert gewartet == [1.5]
    assert len(discord["gesendet"]) == 2


def test_zweimal_429_gibt_fehler(discord):
    discord["antworten"] = [FalscheAntwort(429, {"retry_after": 1}), FalscheAntwort(429, {"retry_after": 1})]
    with pytest.raises(DiscordFehler, match="bremst"):
        DiscordWebhook(WEBHOOK, schlafen=lambda s: None).sende(text="Hallo")


@pytest.mark.parametrize("falsch", ["", "https://example.com/webhook", "discord.com/api/webhooks/1/abc"])
def test_falscher_link_wird_erkannt(falsch):
    with pytest.raises(DiscordFehler, match="DISCORD_WEBHOOK_URL"):
        DiscordWebhook(falsch)


def test_geheimer_link_nie_in_fehlermeldung(monkeypatch):
    def kaputt(url, **kwargs):
        # Echte requests-Fehler enthalten die komplette Adresse – mit dem geheimen Teil
        raise requests.ConnectionError(f"Verbindung zu {url} fehlgeschlagen")

    monkeypatch.setattr(discord_modul.requests, "post", kaputt)
    with pytest.raises(DiscordFehler) as info:
        DiscordWebhook(WEBHOOK).sende(text="Hallo")
    assert "GEHEIMER" not in str(info.value)
    assert info.value.__suppress_context__
