"""Modelos de datos del proyecto (contratos Pydantic).

Cada dato que entra al pipeline pasa por estas clases. Si algo no
cumple el esquema, Pydantic lanza un error explícito en el ETL,
no un bug silencioso en la simulación.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Confederation(str, Enum):
    UEFA = "UEFA"
    CONMEBOL = "CONMEBOL"
    CONCACAF = "CONCACAF"
    CAF = "CAF"
    AFC = "AFC"
    OFC = "OFC"


class Stage(str, Enum):
    GROUP = "Fase de Grupos"
    ROUND_OF_32 = "Dieciseisavos"
    ROUND_OF_16 = "Octavos"
    QUARTER_FINAL = "Cuartos"
    SEMI_FINAL = "Semifinal"
    THIRD_PLACE = "Tercer Puesto"
    FINAL = "Final"


class Team(BaseModel):
    """Una selección nacional con sus datos crudos (pre-procesamiento)."""

    name: str = Field(min_length=2, max_length=50)
    fifa_code: str = Field(min_length=3, max_length=3)
    group: str = Field(pattern=r"^[A-L]$")
    confederation: Confederation
    fifa_rank: int = Field(ge=1, le=211)
    wc_titles: int = Field(ge=0, le=5)
    wc_appearances: int = Field(ge=0, le=23)
    best_finish: float = Field(ge=0.0, le=1.0, description="0=nunca jugó, 1=campeón")
    form_last10: str = Field(pattern=r"^[WDL]{10}$", description="Últimos 10: W/D/L")
    xg_for: float = Field(gt=0, le=5, description="xG promedio a favor")
    xg_against: float = Field(gt=0, le=5, description="xG promedio en contra")
    elo_rating: int | None = Field(
        default=None, ge=1000, le=2500,
        description="ELO actual de eloratings.net (se inyecta en el ETL, no esta en el CSV)"
    )
    squad_value_meur: float | None = Field(
        default=None, ge=0, le=2000,
        description="Valor total de plantilla en M€ (Transfermarkt; inyectado en ETL)"
    )
    avg_age: float | None = Field(
        default=None, ge=18, le=40,
        description="Edad promedio de la plantilla (Transfermarkt; inyectado en ETL)"
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return " ".join(v.strip().split())

    @field_validator("fifa_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()


class TeamStrength(BaseModel):
    """Salida del pipeline: la fuerza calculada de un equipo.

    Implementa el modelo de pesos del proyecto:
      prior (20%)      -> historia mundialista + ranking FIFA
      likelihood (50%) -> forma reciente + xG
      posterior (70%)  -> base estadística = (prior + likelihood) renormalizado
      contexto (30%)   -> se inyecta en tiempo de simulación (clima, lesiones...)
    """

    fifa_code: str
    name: str
    group: str
    prior: float = Field(ge=0.0, le=1.0)
    likelihood: float = Field(ge=0.0, le=1.0)
    posterior: float = Field(ge=0.0, le=1.0)
    att: float = Field(default=1.0, ge=0.2, le=2.5,
                       description="Multiplicador de ataque (1.0 = promedio del torneo)")
    defe: float = Field(default=1.0, ge=0.2, le=2.5,
                        description="Multiplicador defensivo (>1 = concede más que el promedio)")
    resilience: float = Field(default=0.5, ge=0.0, le=1.0,
                              description="Capacidad de competir vs equipos superiores (0=frágil, 1=temple). "
                                          "Se aplica como bonus defensivo SOLO cuando hay brecha de clase.")

    def final_strength(self, context: float = 0.5) -> float:
        """Fuerza final = 70% posterior + 30% contexto del partido.

        `context` vive en [0, 1]; 0.5 es neutro (sin noticias, clima normal).
        """
        context = min(1.0, max(0.0, context))
        return 0.70 * self.posterior + 0.30 * context


class MatchResult(BaseModel):
    """El resultado de un partido simulado."""

    stage: Stage
    home: str
    away: str
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    went_to_extra_time: bool = False
    went_to_penalties: bool = False
    penalty_winner: str | None = None
    news: list[str] = Field(default_factory=list, description="Eventos canónicos del partido")

    @model_validator(mode="after")
    def teams_differ(self) -> "MatchResult":
        if self.home == self.away:
            raise ValueError(f"Un equipo no puede jugar contra sí mismo: {self.home}")
        return self

    @property
    def winner(self) -> str | None:
        if self.went_to_penalties:
            return self.penalty_winner
        if self.home_goals > self.away_goals:
            return self.home
        if self.away_goals > self.home_goals:
            return self.away
        return None  # empate (solo válido en fase de grupos)

    @property
    def scoreline(self) -> str:
        extra = " (pen.)" if self.went_to_penalties else (" (pró.)" if self.went_to_extra_time else "")
        return f"{self.home} {self.home_goals}-{self.away_goals} {self.away}{extra}"


class GroupStanding(BaseModel):
    """Posición de un equipo dentro de su grupo."""

    fifa_code: str
    points: int = Field(ge=0, le=9)
    goals_for: int = Field(ge=0)
    goals_against: int = Field(ge=0)
    played: int = Field(ge=0, le=3)

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against
