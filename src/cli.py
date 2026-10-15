"""CLI del simulador.

Uso:
  python -m src.cli etl                            # pipeline ETL
  python -m src.cli simulate --seed 42             # una copa (cuadro oficial FIFA)
  python -m src.cli montecarlo -n 2000             # probabilidades de campeón
  python -m src.cli h2h BRA MAR -n 10000           # cara a cara (contexto neutro)
  python -m src.cli h2h BRA MAR --ctx-home 0.36    # con noticias (p.ej. figura lesionada)
  python -m src.cli h2h BRA MAR --group            # partido de fase de grupos (admite empate)
  python -m src.cli backtest [--refit]             # calibración vs los 104 partidos reales
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from src.agents.narrator import narrate
from src.etl.models import Stage, TeamStrength
from src.etl.pipeline import run_pipeline
from src.evaluation import backtest
from src.simulation.match_engine import simulate_match
from src.simulation.tournament import GROUPS, TournamentSimulator, monte_carlo

PROCESSED = Path("data/processed/strengths_2026.json")
PHASES = ["Dieciseisavos", "Octavos", "Cuartos", "Semifinal", "Tercer puesto", "Final"]


def load_strengths() -> list[TeamStrength]:
    if not PROCESSED.exists():
        print("ℹ️  No hay datos procesados; corriendo ETL primero...")
        return run_pipeline()
    data = json.loads(PROCESSED.read_text(encoding="utf-8"))
    return [TeamStrength(**row) for row in data]


def cmd_simulate(args: argparse.Namespace) -> None:
    strengths = load_strengths()
    sim = TournamentSimulator(strengths, seed=args.seed)  # sin breaking news
    res = sim.run()

    print("\n" + "=" * 62)
    print("🏆 COPA DEL MUNDO 2026 — SIMULACIÓN (cuadro oficial FIFA)")
    print("=" * 62)

    print("\n📊 FASE DE GRUPOS")
    qual_thirds = set(res.third_slot_assign.values())
    for g in GROUPS:
        print(f"\n  Grupo {g}:")
        for pos, st in enumerate(res.group_tables[g], 1):
            mark = "✅" if pos <= 2 else ("🟡" if pos == 3 and g in qual_thirds else "  ")
            print(f"   {mark} {pos}. {st.fifa_code}  {st.points} pts  (GD {st.goal_diff:+d})")

    for phase in PHASES:
        print(f"\n⚔️  {phase.upper()}")
        for m in res.knockout[phase]:
            print(f"   {narrate(m, use_llm=args.llm)}")

    print("\n" + "=" * 62)
    print(f"🥇 CAMPEÓN:      {res.champion}")
    print(f"🥈 Subcampeón:   {res.runner_up}")
    print(f"🥉 Tercer lugar: {res.third_place}")
    print("=" * 62)


def cmd_montecarlo(args: argparse.Namespace) -> None:
    strengths = load_strengths()
    print(f"🎲 Corriendo {args.n} mundiales con el cuadro oficial...")
    probs = monte_carlo(strengths, n=args.n, seed=args.seed)
    top = sorted(probs.items(), key=lambda kv: kv[1]["champion"], reverse=True)[:15]
    print(f"\n{'Equipo':<8}{'Campeón':>10}{'Finalista':>12}{'Semis':>10}")
    print("-" * 40)
    for code, p in top:
        print(f"{code:<8}{p['champion']:>9.1%}{p['final']:>11.1%}{p['semis']:>9.1%}")


def cmd_h2h(args: argparse.Namespace) -> None:
    strengths = {t.fifa_code: t for t in load_strengths()}
    a, b = strengths[args.team_a.upper()], strengths[args.team_b.upper()]
    rng = random.Random(args.seed)
    stage = Stage.GROUP if args.group else Stage.ROUND_OF_16
    ctx_a = args.ctx_home if args.ctx_home is not None else 0.5
    ctx_b = args.ctx_away if args.ctx_away is not None else 0.5

    wins_a = wins_b = draws = 0
    for _ in range(args.n):
        m = simulate_match(a, b, stage, rng, ctx_a, ctx_b)
        if m.winner == a.fifa_code:
            wins_a += 1
        elif m.winner == b.fifa_code:
            wins_b += 1
        else:
            draws += 1

    mode = "fase de grupos" if args.group else "eliminación directa"
    print(f"\n⚔️  {a.name} vs {b.name}  ({args.n} simulaciones, {mode})")
    line = f"   {a.fifa_code}: {wins_a / args.n:.1%}"
    if args.group:
        line += f"   |   Empate: {draws / args.n:.1%}"
    line += f"   |   {b.fifa_code}: {wins_b / args.n:.1%}"
    print(line)
    print(f"   (posterior {a.fifa_code}={a.posterior:.3f} ctx={ctx_a:.2f}, "
          f"{b.fifa_code}={b.posterior:.3f} ctx={ctx_b:.2f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="World Cup Predictor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("etl", help="Corre el pipeline ETL")

    p_sim = sub.add_parser("simulate", help="Simula una copa completa (cuadro oficial)")
    p_sim.add_argument("--seed", type=int, default=None)
    p_sim.add_argument("--llm", action="store_true", help="Crónicas con Claude")

    p_mc = sub.add_parser("montecarlo", help="N copas -> probabilidades")
    p_mc.add_argument("-n", type=int, default=1000)
    p_mc.add_argument("--seed", type=int, default=None)

    p_h2h = sub.add_parser("h2h", help="Cara a cara entre dos equipos")
    p_h2h.add_argument("team_a")
    p_h2h.add_argument("team_b")
    p_h2h.add_argument("-n", type=int, default=10000)
    p_h2h.add_argument("--seed", type=int, default=None)
    p_h2h.add_argument("--group", action="store_true", help="Partido de grupos (admite empate)")
    p_h2h.add_argument("--ctx-home", type=float, default=None, help="Contexto equipo A [0-1], 0.5 neutro")
    p_h2h.add_argument("--ctx-away", type=float, default=None, help="Contexto equipo B [0-1]")

    p_bt = sub.add_parser("backtest", help="Calibración contra los resultados reales del 2026")
    p_bt.add_argument("--refit", action="store_true",
                      help="Reajusta K/BASE/ρ en grupos y los valida en eliminatorias")

    args = parser.parse_args()
    if args.cmd == "etl":
        run_pipeline()
    elif args.cmd == "simulate":
        cmd_simulate(args)
    elif args.cmd == "montecarlo":
        cmd_montecarlo(args)
    elif args.cmd == "h2h":
        cmd_h2h(args)
    elif args.cmd == "backtest":
        backtest.main(refit=args.refit)


if __name__ == "__main__":
    main()
