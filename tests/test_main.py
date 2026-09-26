"""Tests für die Aktionen von python -m bot."""

import pytest

from bot import __main__ as start
from bot import whatsapp as whatsapp_modul


class FalscheAntwort:
    status_code = 200
    text = "Message queued. You will receive it in a few seconds."


@pytest.fixture
def gesendet(monkeypatch):
    """Ersetzt CallMeBot durch eine Attrappe und merkt sich die Nachrichten."""
    liste = []

    def falsches_get(url, params, timeout):
        liste.append(params)
        return FalscheAntwort()

    monkeypatch.setattr(whatsapp_modul.requests, "get", falsches_get)
    return liste


@pytest.fixture(autouse=True)
def keine_secrets(monkeypatch):
    """Jeder Test startet ohne Secrets (leere Werte überschreibt auch keine .env)."""
    for name in ("WHATSAPP_NUMMER", "CALLMEBOT_APIKEY", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY"):
        monkeypatch.setenv(name, "")


def test_normaler_lauf_klappt_auch_ohne_secrets():
    assert start.main(["normaler-lauf"]) == 0


def test_ohne_aktion_ist_es_ein_normaler_lauf():
    assert start.main([]) == 0


def test_test_nachricht_ohne_secrets_schlaegt_fehl(gesendet):
    assert start.main(["test-nachricht"]) == 1
    assert gesendet == []


def test_test_nachricht_wird_gesendet(monkeypatch, gesendet):
    monkeypatch.setenv("WHATSAPP_NUMMER", "+49 170 1234567")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "123456")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "ich/Ping-Bot-")

    assert start.main(["test-nachricht"]) == 0

    nachricht = gesendet[0]
    assert nachricht["phone"] == "+491701234567"
    assert "Bot läuft" in nachricht["text"]
    assert "https://github.com/ich/Ping-Bot-/actions" in nachricht["text"]


def test_falsche_nummer_gibt_fehlercode(monkeypatch, gesendet):
    monkeypatch.setenv("WHATSAPP_NUMMER", "0170 1234567")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "123456")
    assert start.main(["test-nachricht"]) == 1
    assert gesendet == []


def test_config_fehler_beendet_mit_fehlercode(monkeypatch, tmp_path):
    kaputt = tmp_path / "config.yaml"
    kaputt.write_text("standard_regeln:\n  max_pries: 1\n", encoding="utf-8")
    original = start.lade_einstellungen
    monkeypatch.setattr(start, "lade_einstellungen", lambda: original(kaputt))
    assert start.main(["normaler-lauf"]) == 1
