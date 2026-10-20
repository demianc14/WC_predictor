"""Narrador del torneo.

Dos modos:
  - offline (default): plantillas f-string, no requiere API key.
  - LLM: si ANTHROPIC_API_KEY existe en .env, genera crónicas con Claude.

Esto demuestra el patrón "agente con degradación elegante": el sistema
funciona completo sin el LLM; el LLM solo mejora la experiencia.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from src.etl.models import MatchResult

load_dotenv()


def _offline_narration(match: MatchResult) -> str:
    w = match.winner
    if w is None:
        return f"[{match.stage.value}] Reparto de puntos: {match.scoreline}."
    how = "en los penales" if match.went_to_penalties else (
        "en la prórroga" if match.went_to_extra_time else "en los 90 minutos")
    drama = " ¡Partidazo!" if match.home_goals + match.away_goals >= 5 else ""
    return f"[{match.stage.value}] {w} se impone {how}: {match.scoreline}.{drama}"


def narrate(match: MatchResult, use_llm: bool = False) -> str:
    """Crónica de un partido. `use_llm=True` requiere ANTHROPIC_API_KEY."""
    if not use_llm or not os.getenv("ANTHROPIC_API_KEY"):
        return _offline_narration(match)

    try:
        import anthropic

        client = anthropic.Anthropic()
        news = ("Contexto previo: " + "; ".join(match.news)) if match.news else ""
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Eres un relator deportivo. Escribe una crónica de 2 frases, "
                    f"vibrante y en español, del partido de {match.stage.value} "
                    f"del Mundial 2026: {match.scoreline}. {news}"
                ),
            }],
        )
        return msg.content[0].text.strip()
    except Exception:  # noqa: BLE001 - sin red o sin créditos: degradar
        return _offline_narration(match)
