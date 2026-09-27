"""Tests für das höfliche Abrufen von Shop-Seiten – ohne echtes Internet."""

import pytest
import requests

from bot.abruf import Abrufer, sperre_erkennen

UA = "PokemonPreisBot/0.2 (Test)"


class Antwort:
    def __init__(self, text="", status_code=200, url="https://www.shop.de/x"):
        self.text = text
        self.status_code = status_code
        self.url = url


class FalscheSitzung:
    """Liefert vorbereitete Antworten je Adresse und merkt sich alle Anfragen."""

    def __init__(self, antworten: dict):
        self.antworten = antworten
        self.anfragen = []

    def get(self, url, headers, timeout):
        self.anfragen.append({"url": url, "headers": headers})
        antwort = self.antworten.get(url, Antwort(status_code=404, url=url))
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


def abrufer(antworten, uhr_werte=None):
    sitzung = FalscheSitzung(antworten)
    gewartet = []
    zeiten = iter(uhr_werte or [0.0] * 50)
    a = Abrufer(UA, pause_sekunden=5, sitzung=sitzung, schlafen=gewartet.append, uhr=lambda: next(zeiten))
    return a, sitzung, gewartet


ROBOTS_OK = Antwort("User-agent: *\nDisallow:\n")


def test_normale_seite_mit_ehrlichem_user_agent():
    a, sitzung, _ = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK,
                             "https://www.shop.de/p": Antwort("<html>ok</html>")})
    seite = a.hole("https://www.shop.de/p")
    assert seite.text == "<html>ok</html>"
    assert not seite.gesperrt
    assert sitzung.anfragen[-1]["headers"]["User-Agent"] == UA


def test_robots_txt_verbietet():
    a, sitzung, _ = abrufer({"https://www.shop.de/robots.txt": Antwort("User-agent: *\nDisallow: /\n")})
    seite = a.hole("https://www.shop.de/p")
    assert seite.gesperrt
    assert "robots.txt" in seite.problem
    # Die Produktseite wurde gar nicht erst angefragt
    assert [x["url"] for x in sitzung.anfragen] == ["https://www.shop.de/robots.txt"]


def test_robots_txt_wird_nur_einmal_geladen():
    a, sitzung, _ = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK,
                             "https://www.shop.de/a": Antwort("a"), "https://www.shop.de/b": Antwort("b")})
    a.hole("https://www.shop.de/a")
    a.hole("https://www.shop.de/b")
    assert [x["url"] for x in sitzung.anfragen].count("https://www.shop.de/robots.txt") == 1


def test_keine_robots_txt_heisst_alles_erlaubt():
    a, _, _ = abrufer({"https://www.shop.de/p": Antwort("ok")})  # robots.txt → 404
    assert a.hole("https://www.shop.de/p").text == "ok"


def test_robots_txt_serverfehler_heisst_lieber_nicht_abrufen():
    a, sitzung, _ = abrufer({"https://www.shop.de/robots.txt": Antwort(status_code=500)})
    seite = a.hole("https://www.shop.de/p")
    assert seite.text is None and not seite.gesperrt
    assert len(sitzung.anfragen) == 1


def test_pause_zwischen_anfragen_beim_selben_shop():
    # Uhr: robots.txt endet bei 0 s, die Seite wird bei 1 s angefragt → 4 s warten
    a, _, gewartet = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK,
                              "https://www.shop.de/p": Antwort("ok")}, uhr_werte=[0.0, 1.0, 6.0])
    a.hole("https://www.shop.de/p")
    assert gewartet == [4.0]


@pytest.mark.parametrize(
    "antwort, erwartet",
    [
        (Antwort(status_code=403), "403"),
        (Antwort(status_code=429), "429"),
        (Antwort("<html><title>Just a moment...</title></html>", 503), "Bot-Schutz"),
        (Antwort("<div id='px-captcha'></div>"), "Bot-Schutz"),
        (Antwort("gesperrt", url="https://banned.games-island.eu/"), "gesperrt"),
    ],
)
def test_sperren_werden_erkannt_und_nicht_umgangen(antwort, erwartet):
    a, sitzung, _ = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK, "https://www.shop.de/p": antwort})
    seite = a.hole("https://www.shop.de/p")
    assert seite.gesperrt
    assert erwartet in seite.problem
    assert len(sitzung.anfragen) == 2  # kein zweiter Versuch, keine Tricks


def test_normale_shopseite_mit_captcha_im_kontaktformular_ist_keine_sperre():
    assert sperre_erkennen(Antwort("<form><div class='g-recaptcha'></div></form> Kontakt captcha")) is None


def test_404_ist_keine_sperre():
    a, _, _ = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK})
    seite = a.hole("https://www.shop.de/weg")
    assert seite.http == 404 and not seite.gesperrt
    assert "404" in seite.problem


def test_netzwerkfehler():
    a, _, _ = abrufer({"https://www.shop.de/robots.txt": ROBOTS_OK,
                       "https://www.shop.de/p": requests.ConnectionError("kaputt")})
    seite = a.hole("https://www.shop.de/p")
    assert seite.text is None and not seite.gesperrt
    assert "nicht erreichbar" in seite.problem


def test_abrufer_speichert_keine_cookies():
    # Sonst merkt sich ein Shop z. B. „50 Treffer pro Seite“ und Listen werden plötzlich länger
    a = Abrufer(UA, pause_sekunden=5)
    assert a._sitzung.cookies._policy.allowed_domains() == []  # keine Domain darf Cookies setzen
