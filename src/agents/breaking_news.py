"""Breaking News Engine — Simulador de Eventos Canónicos.

Esta es la capa de "Contexto Local: 30%". Antes de cada partido,
el motor puede generar eventos aleatorios (lesiones, clima, altura,
euforia...) que mueven el contexto de un equipo respecto del neutro 0.5.

También permite INYECTAR eventos manuales ("extras que el usuario crea"):
    engine.inject("BRA", -0.12, "Neymar fuera por molestias musculares")
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CanonicalEvent:
    """Plantilla de un evento canónico del torneo."""

    event_id: str
    headline: str            # plantilla, {team} se reemplaza por el equipo
    probability: float       # prob. de ocurrir por equipo por partido
    delta_min: float         # impacto mínimo sobre el contexto
    delta_max: float         # impacto máximo sobre el contexto


# Catálogo canónico. delta>0 ayuda al equipo, delta<0 lo perjudica.
CATALOG: list[CanonicalEvent] = [
    CanonicalEvent("star_injury", "🚑 {team}: su figura sale lesionada en el calentamiento", 0.040, -0.18, -0.08),
    CanonicalEvent("keeper_doubt", "🧤 {team}: el arquero titular llega con molestias", 0.035, -0.10, -0.04),
    CanonicalEvent("locker_crisis", "🔥 {team}: rumores de crisis interna en el vestuario", 0.025, -0.12, -0.05),
    CanonicalEvent("heat_wave", "🌡️ Ola de calor de 38°C castiga a {team}", 0.050, -0.08, -0.02),
    CanonicalEvent("altitude_cdmx", "⛰️ {team} sufre la altura de Ciudad de México (2.240 m)", 0.030, -0.10, -0.03),
    CanonicalEvent("fan_wave", "📣 Marea de hinchas de {team} convierte el estadio en local", 0.045, 0.03, 0.10),
    CanonicalEvent("momentum", "⚡ {team} llega en racha histórica y la prensa lo da favorito", 0.040, 0.03, 0.09),
    CanonicalEvent("tactical_leak", "🕵️ Se filtra la táctica del rival: ventaja para {team}", 0.015, 0.04, 0.10),
    CanonicalEvent("red_card_risk", "🟥 {team} pierde a un titular por suspensión", 0.035, -0.09, -0.03),
    CanonicalEvent("storm", "⛈️ Tormenta eléctrica retrasa el partido y enfría a {team}", 0.020, -0.07, -0.02),
]


@dataclass
class BreakingNewsEngine:
    """Genera y acumula eventos. Estado por equipo dentro de un torneo."""

    rng: random.Random
    enabled: bool = True
    injected: dict[str, list[tuple[float, str]]] = field(default_factory=dict)

    def inject(self, fifa_code: str, delta: float, headline: str) -> None:
        """Evento manual del usuario, p.ej. 'Mbappé lesionado' antes de simular."""
        self.injected.setdefault(fifa_code, []).append((delta, headline))

    def roll_for_match(self, fifa_code: str) -> tuple[float, list[str]]:
        """Calcula el contexto [0,1] de un equipo para el próximo partido.

        Retorna (context, titulares_de_noticias).
        """
        context = 0.5
        headlines: list[str] = []

        # 1) Eventos inyectados por el usuario (siempre se aplican)
        for delta, headline in self.injected.get(fifa_code, []):
            context += delta
            headlines.append(headline)

        # 2) Eventos aleatorios del catálogo canónico
        if self.enabled:
            for ev in CATALOG:
                if self.rng.random() < ev.probability:
                    delta = self.rng.uniform(ev.delta_min, ev.delta_max)
                    context += delta
                    headlines.append(ev.headline.format(team=fifa_code))

        return min(1.0, max(0.0, context)), headlines
