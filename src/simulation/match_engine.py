"""Motor de partido v3: Maher (ataque×defensa) + corrección Dixon-Coles.

Dos mejoras validadas por la literatura sobre el Poisson independiente:

1. MAHER (1982): los goles esperados se construyen como
       λ_home = BASE × att_home × def_away × exp(K·ΔS)
   El perfil ofensivo/defensivo (xG normalizado) define CÓMO anota un
   equipo; la diferencia de clase global (posterior + contexto) define
   CUÁNTO domina. Dos equipos del mismo nivel pueden producir partidos
   muy distintos según sus perfiles.

2. DIXON-COLES (1997): el Poisson independiente subestima 0-0 y 1-1 y
   sobreestima 1-0 y 0-1. El factor τ(ρ) corrige exactamente esas
   cuatro celdas. Con ρ≈−0.13 (calibración estándar de la literatura),
   el modelo mejora ~15% la precisión en marcadores reales.

El muestreo Dixon-Coles se hace por RECHAZO (rejection sampling):
exacto, sin construir la matriz completa de marcadores.
"""
from __future__ import annotations

import math
import random

from src.etl.models import MatchResult, Stage, TeamStrength

BASE = 1.40        # goles promedio por equipo (calibrado al arranque goleador del
                   # MD2026: ~3.05 goles/partido reales vs 2.6 histórico). Escala ambos
                   # λ por igual → no altera el balance 1X2 (la calibración de K vale).
K = 1.2            # sensibilidad a la diferencia de clase. Calibrado con set BALANCEADO
                   # (5 upsets + 4 esperados): el optimo depende de la tasa de upsets
                   # asumida (50/50→0.8, 70/30→1.6). 1.2 es la eleccion robusta que
                   # funciona en todo el rango realista. Ver tools/calibrate_k.py
RHO = -0.13        # correlación Dixon-Coles para marcadores bajos
MIN_LAMBDA, MAX_LAMBDA = 0.15, 4.5
EXTRA_TIME_FACTOR = 1.0 / 3.0  # 30 min de prórroga ≈ 1/3 de la intensidad de 90'

# Resiliencia: aplica un bonus defensivo cuando un equipo enfrenta a otro con
# clara superioridad de clase. Captura el concepto "aguantar al grande".
RESILIENCE_GAP_THRESHOLD = 0.08  # debajo de este gap la resiliencia no actua
RESILIENCE_GAP_SATURATION = 0.35 # gap por encima del cual la intensidad es maxima
RESILIENCE_MAX_REDUCTION = 0.30  # reduccion maxima del defe (resilience=1, gap saturado)


def resilience_modifier(resilience: float, class_gap: float) -> float:
    """Factor multiplicativo del defe segun resiliencia y brecha de clase.

    class_gap = posterior_oponente - posterior_propio (positivo si yo soy el debil).
    - gap < threshold: factor = 1.0 (no aplica)
    - threshold <= gap <= saturation: rampa lineal
    - gap > saturation: intensidad maxima
    """
    if class_gap <= RESILIENCE_GAP_THRESHOLD:
        return 1.0
    intensity = min(1.0, (class_gap - RESILIENCE_GAP_THRESHOLD) /
                    (RESILIENCE_GAP_SATURATION - RESILIENCE_GAP_THRESHOLD))
    # resilience 0.5 (neutro) => sin efecto; >0.5 reduce defe; <0.5 lo empeora (poco).
    bonus = (resilience - 0.5) * 2  # ahora en [-1, 1]
    return 1.0 - RESILIENCE_MAX_REDUCTION * intensity * bonus


def expected_goals_pair(
    home: TeamStrength, away: TeamStrength,
    ctx_home: float = 0.5, ctx_away: float = 0.5,
    k: float = K,
    base: float = BASE,
) -> tuple[float, float]:
    """(λ_home, λ_away) con el modelo Maher + clase global.

    `k` y `base` por defecto son las constantes del módulo; se pueden
    overridear desde calibración (ver src/evaluation/backtest.py).
    """
    s_h = home.final_strength(ctx_home)
    s_a = away.final_strength(ctx_away)
    # Resiliencia condicional: el equipo "debil" en clase recibe un bonus
    # defensivo si tiene historial de aguantar a grandes. Asimetrico:
    # solo actua cuando hay brecha (la "calidad media" ya esta capturada
    # por prior+likelihood).
    defe_home_eff = home.defe * resilience_modifier(home.resilience, s_a - s_h)
    defe_away_eff = away.defe * resilience_modifier(away.resilience, s_h - s_a)
    lam_h = base * home.att * defe_away_eff * math.exp(k * (s_h - s_a))
    lam_a = base * away.att * defe_home_eff * math.exp(k * (s_a - s_h))

    def clamp(x: float) -> float:
        return min(MAX_LAMBDA, max(MIN_LAMBDA, x))

    return clamp(lam_h), clamp(lam_a)


def penalty_win_probability(s_home: float, s_away: float) -> float:
    """P(gana el home la tanda): moneda cargada por la diferencia de clase."""
    return min(0.78, max(0.22, 0.5 + 0.55 * (s_home - s_away)))


def poisson_sample(lam: float, rng: random.Random) -> int:
    """Muestreo de Poisson (algoritmo de Knuth)."""
    threshold = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def tau(x: int, y: int, lam: float, mu: float, rho: float = RHO) -> float:
    """Factor de corrección Dixon-Coles. Solo toca (0,0),(0,1),(1,0),(1,1)."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def sample_score_dc(lam: float, mu: float, rng: random.Random) -> tuple[int, int]:
    """Muestrea (goles_home, goles_away) de la distribución Dixon-Coles.

    Rejection sampling: P_DC(x,y) ∝ P_Poisson(x,y)·τ(x,y). Se propone con
    el Poisson independiente y se acepta con probabilidad τ/c, donde
    c = max τ posible. Con ρ<0, max τ = max(1−ρ, 1−λμρ). Tasa de rechazo
    típica < 15%.
    """
    c = max(1.0 - RHO, 1.0 - lam * mu * RHO)
    while True:
        x = poisson_sample(lam, rng)
        y = poisson_sample(mu, rng)
        if rng.random() * c <= tau(x, y, lam, mu):
            return x, y


def simulate_match(
    home: TeamStrength,
    away: TeamStrength,
    stage: Stage,
    rng: random.Random,
    context_home: float = 0.5,
    context_away: float = 0.5,
    news: list[str] | None = None,
) -> MatchResult:
    """Simula un partido completo con el modelo Maher + Dixon-Coles."""
    lam_h, lam_a = expected_goals_pair(home, away, context_home, context_away)
    hg, ag = sample_score_dc(lam_h, lam_a, rng)

    is_knockout = stage != Stage.GROUP
    went_et = went_pens = False
    pen_winner: str | None = None

    if is_knockout and hg == ag:
        went_et = True
        # Prórroga: 30 min ≈ 1/3 de intensidad; Poisson simple (DC corrige
        # marcadores de partido completo, no fracciones de tiempo)
        hg += poisson_sample(lam_h * EXTRA_TIME_FACTOR, rng)
        ag += poisson_sample(lam_a * EXTRA_TIME_FACTOR, rng)
        if hg == ag:
            went_pens = True
            p_home = penalty_win_probability(home.final_strength(context_home),
                                             away.final_strength(context_away))
            pen_winner = home.fifa_code if rng.random() < p_home else away.fifa_code

    return MatchResult(
        stage=stage,
        home=home.fifa_code,
        away=away.fifa_code,
        home_goals=hg,
        away_goals=ag,
        went_to_extra_time=went_et,
        went_to_penalties=went_pens,
        penalty_winner=pen_winner,
        news=news or [],
    )
