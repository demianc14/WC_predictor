"""Champions 2026-27: próximos partidos 1X2 y Monte Carlo de la fase de liga y del cuadro.

    python -m src.europe.run            # escribe data/processed/ucl.json

Usa el Dixon-Coles conjunto (`src/europe/data.py`), ajustado con todo lo
jugado antes de hoy. La fase de liga son 8 jornadas, 36 clubes en una sola
tabla: del 1 al 8 pasan a octavos, del 9 al 24 juegan el playoff y del 25 al
36 quedan afuera. El desempate es puntos, diferencia, goles a favor y azar:
una simplificación del reglamento de la UEFA, que después mira goles de
visita, victorias y la fuerza de los rivales.

Cada corrida sigue con las eliminatorias del cuadro oficial (`knockout.py`), así
que también salen P(octavos), P(cuartos), P(semis), P(final) y P(campeón).

Partidos de eliminatorias (T2). En el feed son las rondas 9 a 17 (medido en
2024-25 y 2025-26): playoff 9/10, octavos 11/12, cuartos 13/14, semis 15/16 y
final 17. Una ronda entra solo si llega completa y con todos sus clubes con
rating; si no, se salta entera y se avisa (`ko_status`), porque lo guardado no
se puede corregir. El marcador del feed no distingue la prórroga, así que al
almacén solo van las idas (`STORED_KO`), que nunca la tienen. Las vueltas y la
final se muestran, sin guardarse, y la final se predice en cancha neutral.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from src.clubs import calendar
from src.clubs.backtest import _outcome
from src.clubs.data import Match
from src.clubs.model import XI, Ratings, fit
from src.clubs.run import _pred
from src.clubs.season import current_table
from src.europe import backtest, knockout
from src.europe import data as eu
from src.ml import europe

OUT = Path("data/processed/ucl.json")
FEED, YEAR, COMP = "champions-league", 2026, "UCL"
SEASON = eu.season_of(YEAR)
LEAGUE_ROUNDS, TEAMS = 8, 36
ZONES = {"octavos": (1, 8), "playoff": (9, 24), "afuera": (25, 36)}
NEXT_DAYS = 7
KO_ROUNDS = {9: 8, 10: 8, 11: 8, 12: 8, 13: 4, 14: 4, 15: 2, 16: 2, 17: 1}   # partidos
STORED_KO = (9, 11, 13, 15)          # idas: sin prórroga, el marcador es el de los 90'
FINAL = 17
KO_LATE_DAYS = 14                    # sin playoff publicado tantos días después de la J8: aviso


def _named(f: calendar.Fixture) -> calendar.Fixture:
    return calendar.Fixture(f.round, f.day, eu.name(f.home), eu.name(f.away), f.hg, f.ag, f.tbc)


def league_phase(rows: list[dict]) -> list[calendar.Fixture]:
    return [_named(f) for f in calendar.parse_calendar(rows) if f.round <= LEAGUE_ROUNDS]


def knockout_phase(rows: list[dict], rated: set[str]
                   ) -> tuple[list[calendar.Fixture], list[str]]:
    """Las rondas de eliminatorias que llegaron completas y con clubes conocidos, y por
    qué se saltó cada una de las otras."""
    by_round: dict[int, list[calendar.Fixture]] = {}
    for f in calendar.parse_calendar(rows):
        if f.round > LEAGUE_ROUNDS:
            by_round.setdefault(f.round, []).append(_named(f))
    out, skipped = [], []
    for rnd, fx in sorted(by_round.items()):
        teams = [t for f in fx for t in (f.home, f.away)]
        unknown = sorted({t for t in teams if t not in rated})
        if rnd not in KO_ROUNDS:
            skipped.append(f"ronda {rnd}: no existe en el formato ({len(fx)} partidos)")
        elif len(fx) != KO_ROUNDS[rnd]:
            skipped.append(f"ronda {rnd}: {len(fx)} partidos (se esperan {KO_ROUNDS[rnd]})")
        elif unknown:
            skipped.append(f"ronda {rnd}: clubes sin rating {unknown}")
        elif len(set(teams)) != len(teams):
            skipped.append(f"ronda {rnd}: un club juega dos veces")
        else:
            out += fx
    return out, skipped


def ko_next(r: Ratings, ko: list[calendar.Fixture], today: date) -> list[dict]:
    """Eliminatorias de los próximos días. `stored` dice si van al almacén."""
    neutral = replace(r, home=1.0)
    return [{"day": f.day.isoformat(), "round": f.round, "ko_round": f.round,
             "home": f.home, "away": f.away, "stored": f.round in STORED_KO,
             "neutral": f.round == FINAL,
             **_pred(neutral if f.round == FINAL else r, f.home, f.away)}
            for f in ko if today <= f.day < today + timedelta(days=NEXT_DAYS)]


def ko_results(ko: list[calendar.Fixture], today: date) -> list[list]:
    """Idas ya jugadas, con su ronda, para completar el almacén."""
    return [[f.round, f.day.isoformat(), f.home, f.away, f.hg, f.ag]
            for f in ko if f.round in STORED_KO and f.played and f.day < today]


def ko_status(league: list[calendar.Fixture], ko: list[calendar.Fixture],
              skipped: list[str], today: date) -> dict:
    """sin_publicar, publicado, incompleto (alguna ronda saltada) o atrasado (la fase de
    liga terminó hace más de KO_LATE_DAYS días y el playoff no está)."""
    if skipped:
        state = "incompleto"
    elif ko:
        state = "publicado"
    else:
        done = bool(league) and all(f.played for f in league)
        last = max((f.day for f in league), default=today)
        state = "atrasado" if done and (today - last).days > KO_LATE_DAYS else "sin_publicar"
    return {"state": state, "rounds": sorted({f.round for f in ko}), "skipped": skipped}


def base_rates(matches: list[Match]) -> list[float]:
    """1/X/2 de la Champions antes de esta temporada: la base, fija y conocida de antemano."""
    n = [1, 1, 1]
    for m in matches:
        if m.div == COMP and m.played and m.season < SEASON:
            n[_outcome(m)] += 1
    return [round(c / sum(n), 4) for c in n]


def build(today: date | None = None, sims: int = 10000, with_backtest: bool = True) -> dict:
    today = today or date.today()
    p = europe.ensure(FEED, YEAR)
    if p is None:
        raise FileNotFoundError(f"sin el feed {FEED}-{YEAR}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    cal = league_phase(raw)
    shown = {eu.name(r[k]): r[k] for r in raw for k in ("HomeTeam", "AwayTeam")}   # el del feed
    ms = eu.load()
    r = fit(ms, today)
    teams = sorted({f.home for f in cal} | {f.away for f in cal})
    if len(teams) != TEAMS or len(cal) != TEAMS * LEAGUE_ROUNDS // 2:
        raise ValueError(f"Champions: {len(teams)} clubes y {len(cal)} partidos en la fase de liga")
    missing = [t for t in teams if t not in r.att]
    if missing:
        raise ValueError(f"Champions: sin rating para {missing}")

    played = [Match(COMP, SEASON, f.day, f.home, f.away, f.hg, f.ag)
              for f in cal if f.played and f.day < today]
    pending = [f for f in cal if not (f.played and f.day < today)]
    table = current_table(played, teams)
    proj = knockout.simulate(r, played, teams, [(f.home, f.away) for f in pending], n=sims)
    alone = eu.without_league(ms)
    league_of = {t: m.div for m in ms if m.div not in eu.COMPS.values() and m.season == SEASON
                 for t in (m.home, m.away)}
    nxt = [{"day": f.day.isoformat(), "round": f.round, "home": f.home, "away": f.away,
            **_pred(r, f.home, f.away)}
           for f in pending if today <= f.day < today + timedelta(days=NEXT_DAYS)]
    ko, skipped = knockout_phase(raw, set(r.att))
    status = ko_status(cal, ko, skipped, today)
    if status["state"] in ("incompleto", "atrasado"):          # degradación: avisa y sigue
        print(f"⚠️  Champions, eliminatorias {status['state']}: "
              + ("; ".join(skipped) or f"sin playoff en el feed {FEED}-{YEAR}"))
    nxt += ko_next(r, ko, today)
    rest =[[f.round, f.day.isoformat(), f.home, f.away,
             *(round(p, 3) for p in r.probs(f.home, f.away)[:3])]
            for f in pending if f.day >= today + timedelta(days=NEXT_DAYS)]

    out = {
        "comp": COMP, "season": SEASON, "fitted": today.isoformat(),
        "updated": max((m.day for m in played), default=today).isoformat(),
        "params": {"mu": r.mu, "home": r.home, "rho": r.rho, "xi": XI},
        "zones": ZONES, "played": len(played), "remaining": len(pending),
        "base": base_rates(ms),
        "teams": [{"t": t, "n": shown.get(t, t), "league": league_of.get(t),
                   "no_league": t in alone, "n_eff": r.n_eff[t], "att": r.att[t],
                   "def": r.defe[t], **table[t], **proj[t],
                   **{z: round(sum(proj[t]["pos"][a - 1:b]), 4) for z, (a, b) in ZONES.items()}}
                  for t in teams],
        "next": nxt, "calendar": rest,
        # lo jugado de la fase de liga, para que el ciclo diario complete el almacén
        "results": [[m.day.isoformat(), m.home, m.away, m.hg, m.ag] for m in played],
        "ko_results": ko_results(ko, today), "ko": status,
    }
    if with_backtest:
        rows = backtest.walk_forward(ms, backtest.TEST)
        rep = backtest.report(rows)
        out["backtest"] = {"seasons": list(backtest.TEST), "model": rep["model"],
                           "base": rep["base"], "diff_rps": rep["diff"]["rps"]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Champions 2026-27: partidos y fase de liga")
    ap.add_argument("-n", type=int, default=10000)
    args = ap.parse_args()
    out = build(sims=args.n)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(out["teams"], key=lambda t: -t["ko"]["champion"])[:5]
    print(f"✅ Champions: {out['played']} jugados, {out['remaining']} por jugar, "
          f"{len(out['next'])} en los próximos {NEXT_DAYS} días")
    print("   Campeón:", ", ".join(f"{t['t']} {t['ko']['champion']:.0%}" for t in top))


if __name__ == "__main__":
    main()
