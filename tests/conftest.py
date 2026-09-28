"""Gemeinsame Test-Bausteine – pytest findet sie automatisch."""

import pytest

from bot.speicher import Speicher


@pytest.fixture
def speicher(tmp_path):
    """Eine frische, leere Datenbank für jeden Test."""
    s = Speicher(tmp_path / "bot.db")
    yield s
    s.schliessen()
