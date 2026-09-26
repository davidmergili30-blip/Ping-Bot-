"""Tests für die Aktionen von python -m bot."""

import pytest

from bot import __main__ as start
from bot import discord as discord_modul

WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/abcDEF"


class FalscheAntwort:
    status_code = 204


@pytest.fixture
def gesendet(monkeypatch):
    """Ersetzt Discord durch eine Attrappe und merkt sich die Nachrichten."""
    liste = []

    def falsches_post(url, json, params, timeout):
        liste.append(json)
        return FalscheAntwort()

    monkeypatch.setattr(discord_modul.requests, "post", falsches_post)
    return liste


@pytest.fixture(autouse=True)
def keine_secrets(monkeypatch):
    """Jeder Test startet ohne Secrets (leere Werte überschreibt auch keine .env)."""
    for name in ("DISCORD_WEBHOOK_URL", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY"):
        monkeypatch.setenv(name, "")


def test_normaler_lauf_klappt_auch_ohne_secrets():
    assert start.main(["normaler-lauf"]) == 0


def test_ohne_aktion_ist_es_ein_normaler_lauf():
    assert start.main([]) == 0


def test_test_nachricht_ohne_secret_schlaegt_fehl(gesendet):
    assert start.main(["test-nachricht"]) == 1
    assert gesendet == []


def test_test_nachricht_wird_gesendet(monkeypatch, gesendet):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "ich/Ping-Bot-")

    assert start.main(["test-nachricht"]) == 0

    kasten = gesendet[0]["embeds"][0]
    assert "Bot läuft" in kasten["title"]
    assert kasten["url"] == "https://github.com/ich/Ping-Bot-/actions"


def test_falscher_webhook_gibt_fehlercode(monkeypatch, gesendet):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/nicht-discord")
    assert start.main(["test-nachricht"]) == 1
    assert gesendet == []


def test_config_fehler_beendet_mit_fehlercode(monkeypatch, tmp_path):
    kaputt = tmp_path / "config.yaml"
    kaputt.write_text("standard_regeln:\n  max_pries: 1\n", encoding="utf-8")
    original = start.lade_einstellungen
    monkeypatch.setattr(start, "lade_einstellungen", lambda: original(kaputt))
    assert start.main(["normaler-lauf"]) == 1
