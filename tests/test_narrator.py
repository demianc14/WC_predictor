"""El narrador es opcional: sin el paquete anthropic degrada a plantillas."""
import sys

from src.agents.narrator import _offline_narration, narrate
from src.etl.models import MatchResult, Stage


def test_sin_paquete_anthropic_usa_la_plantilla(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setitem(sys.modules, "anthropic", None)       # import anthropic -> ImportError
    m = MatchResult(stage=Stage.GROUP, home="BRA", away="MAR", home_goals=2, away_goals=1)
    assert narrate(m, use_llm=True) == _offline_narration(m)
