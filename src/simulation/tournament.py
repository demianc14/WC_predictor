"""Simulador del torneo completo — formato y CUADRO OFICIAL del Mundial 2026.

48 equipos -> 12 grupos de 4
  -> clasifican los 2 primeros (24) + los 8 mejores terceros
  -> Dieciseisavos (M73-M88, cuadro fijo de FIFA) -> Octavos -> Cuartos
  -> Semifinales -> Tercer puesto (M103) -> Final (M104)

Los terceros entran a la llave que la FIFA permite para su grupo
(p.ej. M74 recibe al tercero de A/B/C/D/F). La asignación se resuelve
con backtracking sobre las combinaciones permitidas.

Las breaking news NO se aplican por defecto: el contexto neutro (0.5)
gobierna grupos, Mundial completo y Monte Carlo. El motor de eventos
se usa solo cuando se inyectan noticias explícitas (engine.inject) o
se activa expresamente (news_enabled=True).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import combinations

from src.agents.breaking_news import BreakingNewsEngine
from src.etl.models import GroupStanding, MatchResult, Stage, TeamStrength
from src.simulation.match_engine import simulate_match

GROUPS = "ABCDEFGHIJKL"
HOSTS = {"USA", "MEX", "CAN"}   # anfitriones 2026: juegan "en casa"
HOST_BONUS = 0.08               # impulso de contexto documentado (~+0.5 goles/equipo local)

# ── Cuadro oficial FIFA 2026 ───────────────────────────────────────
# "1A" = ganador del grupo A · "2A" = segundo · "3:ABCDF" = tercero permitido
R32 = [
    ("M73", "2A", "2B"),      ("M74", "1E", "3:ABCDF"),
    ("M75", "1F", "2C"),      ("M76", "1C", "2F"),
    ("M77", "1I", "3:CDFGH"), ("M78", "2E", "2I"),
    ("M79", "1A", "3:CEFHI"), ("M80", "1L", "3:EHIJK"),
    ("M81", "1D", "3:BEFIJ"), ("M82", "1G", "3:AEHIJ"),
    ("M83", "2K", "2L"),      ("M84", "1H", "2J"),
    ("M85", "1B", "3:EFGIJ"), ("M86", "1J", "2H"),
    ("M87", "1K", "3:DEIJL"), ("M88", "2D", "2G"),
]
R16 = [("M89", "M74", "M77"), ("M90", "M73", "M75"), ("M91", "M76", "M78"),
       ("M92", "M79", "M80"), ("M93", "M83", "M84"), ("M94", "M81", "M82"),
       ("M95", "M86", "M88"), ("M96", "M85", "M87")]
QF = [("M97", "M89", "M90"), ("M98", "M93", "M94"),
      ("M99", "M91", "M92"), ("M100", "M95", "M96")]
SF = [("M101", "M97", "M98"), ("M102", "M99", "M100")]

STAGE_OF = {
    "Dieciseisavos": (R32, Stage.ROUND_OF_32),
    "Octavos": (R16, Stage.ROUND_OF_16),
    "Cuartos": (QF, Stage.QUARTER_FINAL),
    "Semifinal": (SF, Stage.SEMI_FINAL),
}


def assign_thirds(third_groups: list[str]) -> dict[str, str]:
    """Asigna los 8 terceros clasificados a sus llaves permitidas.

    `third_groups` viene ordenado del mejor al peor tercero. Backtracking
    garantiza un emparejamiento válido (FIFA diseñó los slots para que
    siempre exista).
    """
    slots = [(m, b[2:]) for m, _, b in R32 if b.startswith("3:")]
    assign: dict[str, str] = {}

    def bt(i: int, used: set[str]) -> bool:
        if i == len(slots):
            return True
        match_id, allowed = slots[i]
        for g in third_groups:
            if g in used or g not in allowed:
                continue
            assign[match_id] = g
            used.add(g)
            if bt(i + 1, used):
                return True
            del assign[match_id]
            used.remove(g)
        return False

    if not bt(0, set()):  # salvaguarda (no debería ocurrir)
        rest = [g for g in third_groups]
        for m, _ in slots:
            if m not in assign:
                assign[m] = rest.pop(0)
    return assign


@dataclass
class TournamentResult:
    group_matches: dict[str, list[MatchResult]] = field(default_factory=dict)
    group_tables: dict[str, list[GroupStanding]] = field(default_factory=dict)
    knockout: dict[str, list[MatchResult]] = field(default_factory=dict)
    third_slot_assign: dict[str, str] = field(default_factory=dict)
    champion: str = ""
    runner_up: str = ""
    third_place: str = ""


def _winner_of(m: MatchResult) -> str:
    w = m.winner
    assert w is not None
    return w


def _loser_of(m: MatchResult) -> str:
    return m.away if _winner_of(m) == m.home else m.home


class TournamentSimulator:
    def __init__(
        self,
        strengths: list[TeamStrength],
        seed: int | None = None,
        news_enabled: bool = False,
        news_engine: BreakingNewsEngine | None = None,
        fixed_group_results: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """`fixed_group_results`: {"C|0": (0, 5)} fija el partido idx 0 del
        grupo C (orden round-robin sobre los equipos en orden de dataset)."""
        self.rng = random.Random(seed)
        self.teams = {t.fifa_code: t for t in strengths}
        self.news = news_engine or BreakingNewsEngine(rng=self.rng, enabled=news_enabled)
        self.fixed = fixed_group_results or {}
        if len(self.teams) != 48:
            raise ValueError(f"Se esperaban 48 equipos, llegaron {len(self.teams)}")

    def _ctx(self, code: str) -> tuple[float, list[str]]:
        ctx, news = self.news.roll_for_match(code)
        if code in HOSTS:
            ctx = min(1.0, ctx + HOST_BONUS)
        return ctx, news

    # ── Fase de grupos ────────────────────────────────────────────
    def _play_group(self, group: str) -> tuple[list[MatchResult], list[GroupStanding]]:
        codes = [c for c, t in self.teams.items() if t.group == group]
        table = {c: GroupStanding(fifa_code=c, points=0, goals_for=0,
                                  goals_against=0, played=0) for c in codes}
        matches: list[MatchResult] = []

        for idx, (a, b) in enumerate(combinations(codes, 2)):
            fixed = self.fixed.get(f"{group}|{idx}")
            if fixed is not None:
                ga, gb = fixed
                m = MatchResult(stage=Stage.GROUP, home=a, away=b,
                                home_goals=ga, away_goals=gb)
            else:
                ctx_a, na = self._ctx(a)
                ctx_b, nb = self._ctx(b)
                m = simulate_match(self.teams[a], self.teams[b], Stage.GROUP,
                                   self.rng, ctx_a, ctx_b, news=na + nb)
            matches.append(m)
            for code, gf, ga_ in ((a, m.home_goals, m.away_goals),
                                  (b, m.away_goals, m.home_goals)):
                st = table[code]
                pts = 3 if gf > ga_ else (1 if gf == ga_ else 0)
                table[code] = GroupStanding(
                    fifa_code=code, points=st.points + pts,
                    goals_for=st.goals_for + gf, goals_against=st.goals_against + ga_,
                    played=st.played + 1)

        ordered = sorted(table.values(),
                         key=lambda s: (s.points, s.goal_diff, s.goals_for,
                                        self.rng.random()),
                         reverse=True)
        return matches, ordered

    # ── Eliminación directa con el cuadro oficial ─────────────────
    def run(self) -> TournamentResult:
        res = TournamentResult()
        for g in GROUPS:
            res.group_matches[g], res.group_tables[g] = self._play_group(g)

        def key(s):
            return (s.points, s.goal_diff, s.goals_for)

        thirds = sorted(((g, res.group_tables[g][2]) for g in GROUPS),
                        key=lambda t: key(t[1]), reverse=True)
        qual_thirds = [g for g, _ in thirds[:8]]
        res.third_slot_assign = assign_thirds(qual_thirds)

        winners: dict[str, str] = {}

        def resolve(match_id: str, code: str) -> str:
            if code.startswith("M"):
                return winners[code]
            if code.startswith("3:"):
                return res.group_tables[res.third_slot_assign[match_id]][2].fifa_code
            pos, grp = int(code[0]), code[1]
            return res.group_tables[grp][pos - 1].fifa_code

        def play_round(label: str) -> None:
            defs, stage = STAGE_OF[label]
            out = []
            for match_id, x, y in defs:
                ta, tb = resolve(match_id, x), resolve(match_id, y)
                ctx_a, na = self._ctx(ta)
                ctx_b, nb = self._ctx(tb)
                m = simulate_match(self.teams[ta], self.teams[tb], stage,
                                   self.rng, ctx_a, ctx_b, news=na + nb)
                winners[match_id] = _winner_of(m)
                out.append(m)
            res.knockout[label] = out

        for label in ("Dieciseisavos", "Octavos", "Cuartos", "Semifinal"):
            play_round(label)

        semis = res.knockout["Semifinal"]
        l1, l2 = _loser_of(semis[0]), _loser_of(semis[1])
        res.knockout["Tercer puesto"] = [
            simulate_match(self.teams[l1], self.teams[l2], Stage.THIRD_PLACE, self.rng)]
        res.knockout["Final"] = [
            simulate_match(self.teams[winners["M101"]], self.teams[winners["M102"]],
                           Stage.FINAL, self.rng)]

        final = res.knockout["Final"][0]
        res.champion = _winner_of(final)
        res.runner_up = _loser_of(final)
        res.third_place = _winner_of(res.knockout["Tercer puesto"][0])
        return res


# ── Monte Carlo (sin breaking news) ───────────────────────────────

def monte_carlo(strengths: list[TeamStrength], n: int = 1000,
                seed: int | None = None) -> dict[str, dict[str, float]]:
    base = random.Random(seed)
    counts = {t.fifa_code: {"champion": 0, "final": 0, "semis": 0} for t in strengths}
    for _ in range(n):
        sim = TournamentSimulator(strengths, seed=base.randrange(2**32))
        r = sim.run()
        counts[r.champion]["champion"] += 1
        counts[r.champion]["final"] += 1
        counts[r.runner_up]["final"] += 1
        for m in r.knockout["Semifinal"]:
            counts[m.home]["semis"] += 1
            counts[m.away]["semis"] += 1
    return {c: {k: round(v / n, 4) for k, v in d.items()} for c, d in counts.items()}
