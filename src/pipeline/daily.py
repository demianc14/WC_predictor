"""Ciclo diario: datos nuevos → resultados → predicciones → métricas en vivo → web.

    python -m src.pipeline.daily

1. Descarga, una vez cada una, las fuentes vivas (temporada actual de las 10
   divisiones y de las 6 ligas extra del modelo conjunto, fixtures.csv, los 5
   calendarios y los feeds de Champions y Europa League) a una carpeta
   temporal. Si alguna falla o llega vacía, termina con código 2 y no toca nada.
2. Con todo descargado, recién entonces las mueve a la caché.
3. En memoria: ajusta cada liga (Dixon-Coles, igual que la web), arma las
   predicciones de los partidos de los próximos días que aún no tienen una
   para la versión actual del modelo, completa los resultados ya jugados y
   recalcula las métricas en vivo. La Champions (`src/europe/run.py`) entra al
   mismo almacén con `league="UCL"` y su propia versión, pero sus métricas van
   aparte (`ucl` en live.json): no tiene cuotas, se compara contra la base.
4. Solo si todo lo anterior salió bien, escribe: JSON por liga, live.json, el
   almacén (que verifica que no se sobrescribe nada) y la web.

Versión del modelo = hash git del árbol `src/clubs/`: cambia solo si cambia
el código del modelo, no con cualquier commit. La de la Champions junta los
árboles `src/clubs/` y `src/europe/`, porque depende de los dos.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from src.clubs import calendar, data, run
from src.clubs.backtest import no_vig
from src.clubs.leagues import LEAGUES, League
from src.europe import data as eu
from src.ml import europe
from src.ml.metrics import summary
from src.pipeline import store

MODEL = "dixon-coles"
CUTOFF_HOUR_UTC = 10        # un partido de hoy solo se predice si el ciclo corre antes de esta hora
OUT_DIR = Path("data/processed")
LIVE = OUT_DIR / "live.json"
RESULT = {"H": 0, "D": 1, "A": 2}
UCL = "UCL"


class SourceError(RuntimeError):
    pass


def sources(leagues: list[League]) -> list[tuple[str, str, str]]:
    s = data.CURRENT_SEASON
    out = [(data.BASE_URL.format(season=s, div=d), f"{d}_{s}.csv", "csv")
           for lg in leagues for d in (lg.code, lg.lower)]
    out.append((data.FIXTURES_URL, "fixtures.csv", "csv"))
    out += [(calendar.FEED_URL.format(feed=lg.feed, year=calendar.SEASON_YEAR),
             f"calendar_{lg.feed}_{calendar.SEASON_YEAR}.json", "json") for lg in leagues]
    return out


def europe_sources() -> list[tuple[str, str, str]]:
    """Lo vivo del modelo conjunto: ligas extra y los feeds europeos de esta temporada."""
    s, y = data.CURRENT_SEASON, calendar.SEASON_YEAR
    out = [(data.BASE_URL.format(season=s, div=d), f"{d}_{s}.csv", "csv") for d in eu.EXTRA_DIVS]
    out += [(calendar.FEED_URL.format(feed=f, year=y),
             europe.path(f, y).relative_to(data.CACHE_DIR).as_posix(), "json") for f in eu.COMPS]
    return out


def _validate(path: Path, kind: str) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else ""
    if kind == "csv":
        if not text.lstrip().startswith("Div,") or text.count("\n") < 1:
            raise SourceError(f"{path.name}: no es un CSV de football-data")
    else:
        rows = json.loads(text or "null")
        if not isinstance(rows, list) or not rows or "HomeTeam" not in rows[0]:
            raise SourceError(f"{path.name}: calendario vacío o con otro formato")


def fetch(srcs: list[tuple[str, str, str]], cache_dir: Path = data.CACHE_DIR,
          download: Callable[[str, Path], None] = data._download) -> None:
    """Todo o nada: baja y valida cada fuente en un temporal; recién al final reemplaza."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=cache_dir, prefix=".daily-"))
    try:
        for url, name, kind in srcs:
            try:
                download(url, tmp / name)
            except Exception as e:
                raise SourceError(f"{url}: {e}") from e
            _validate(tmp / name, kind)
        for _, name, _ in srcs:
            (cache_dir / name).parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp / name, cache_dir / name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def predictable(day: date, now: datetime) -> bool:
    """Antes del partido: días futuros, o hoy si el ciclo corre temprano (UTC)."""
    today = now.date()
    return day > today or (day == today and now.hour < CUTOFF_HOUR_UTC)


def predictions(outs: dict[str, dict], now: datetime, version: str, commit: str) -> list[dict]:
    rows = []
    for div, out in outs.items():
        for n in out["next"]:
            day = date.fromisoformat(n["day"])
            if not predictable(day, now):
                continue
            p1, px, p2 = n["model"]
            rows.append({
                "match_id": store.match_id(div, data.CURRENT_SEASON, n["home"], n["away"]),
                "league": div, "season": data.CURRENT_SEASON, "match_date": n["day"],
                "home": n["home"], "away": n["away"], "model": MODEL,
                "model_version": version, "commit": commit,
                "predicted_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "p1": f"{p1:.4f}", "px": f"{px:.4f}", "p2": f"{p2:.4f}",
            })
    return rows


def results(matches: list[data.Match]) -> dict[str, dict]:
    out = {}
    for m in matches:
        if not m.played:
            continue
        hg, ag = m.score()
        mk = no_vig(m.odds) if m.odds else ("", "", "")
        out[store.match_id(m.div, m.season, m.home, m.away)] = {
            "result": "H" if hg > ag else "D" if hg == ag else "A",
            "hg": hg, "ag": ag,
            **{c: (f"{v:.4f}" if v != "" else "") for c, v in zip(("mk1", "mkx", "mk2"), mk)}}
    return out


def _metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    y = np.array([RESULT[r["result"]] for r in rows])
    p = np.array([[float(r["p1"]), float(r["px"]), float(r["p2"])] for r in rows])
    out = {"model": summary(y, p)}
    mk = [i for i, r in enumerate(rows) if r["mk1"]]
    if mk:
        q = np.array([[float(rows[i][c]) for c in ("mk1", "mkx", "mk2")] for i in mk])
        out["same_sample"] = {"n": len(mk), "model": summary(y[mk], p[mk]),
                              "market": summary(y[mk], q)}
    return {"n": len(rows), **out}


def _ucl_metrics(rows: list[dict], base: list[float] | None) -> dict:
    """Champions: sin cuotas, contra la base (1/X/2 de temporadas anteriores), misma muestra."""
    out = _metrics(rows)
    if rows and base:
        y = np.array([RESULT[r["result"]] for r in rows])
        out["base"] = summary(y, np.tile(base, (len(rows), 1)))
    return out


def live_metrics(rows: list[dict], now: datetime, ucl_base: list[float] | None = None) -> dict:
    """Métricas de lo que se predijo ANTES de jugarse: la primera predicción de cada partido.

    `all`, `by_league` y `by_version` son las cinco ligas; la Champions va en `ucl`.
    """
    ucl = [r for r in rows if r["league"] == UCL]
    rows = [r for r in rows if r["league"] != UCL]
    ucl_first: dict[str, dict] = {}
    for r in sorted(ucl, key=lambda r: r["predicted_at"]):
        ucl_first.setdefault(r["match_id"], r)
    ucl_done = [r for r in ucl_first.values() if r["result"]]
    first: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: r["predicted_at"]):
        first.setdefault(r["match_id"], r)
    done = [r for r in first.values() if r["result"]]
    by_league = {div: _metrics([r for r in done if r["league"] == div])
                 for div in sorted({r["league"] for r in first.values()})}
    # Cada versión con su propia primera predicción: muestras distintas, se comparan contra el
    # mercado sobre su misma muestra, no entre ellas.
    own: dict[str, dict[str, dict]] = {}
    for r in sorted(rows, key=lambda r: r["predicted_at"]):
        own.setdefault(r["model_version"], {}).setdefault(r["match_id"], r)
    by_version = [{"version": v, "since": min(r["predicted_at"] for r in ms.values()),
                   **_metrics([r for r in ms.values() if r["result"]])}
                  for v, ms in own.items()]
    return {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "since": min((r["predicted_at"] for r in rows), default=None),
        "n_predictions": len(rows), "n_matches": len(first),
        "n_pending": sum(1 for r in first.values() if not r["result"]),
        "all": _metrics(done), "by_league": by_league, "by_version": by_version,
        "ucl": {"n_predictions": len(ucl), "n_matches": len(ucl_first),
                "n_pending": len(ucl_first) - len(ucl_done),
                "versions": sorted({r["model_version"] for r in ucl}),
                **_ucl_metrics(ucl_done, ucl_base)},
    }


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def model_version() -> tuple[str, str]:
    """(versión del modelo, commit). En Docker no hay .git: vienen del build (WCP_*)."""
    version, commit = os.environ.get("WCP_MODEL_VERSION"), os.environ.get("WCP_COMMIT")
    if version and commit and version != "desconocida":
        return version, commit
    try:
        return (_git("rev-parse", "--short", "HEAD:src/clubs"),
                _git("rev-parse", "--short", "HEAD"))
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError("Sin versión del modelo: corre desde el repo con git, o construye "
                           "la imagen con `make docker-build`") from e


def europe_version() -> str:
    """Versión del modelo de la Champions: árboles `src/clubs/` + `src/europe/`."""
    v = os.environ.get("WCP_UCL_VERSION")
    if v and v != "desconocida":
        return v
    try:
        return f"{_git('rev-parse', '--short', 'HEAD:src/clubs')}+" \
               f"{_git('rev-parse', '--short', 'HEAD:src/europe')}"
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError("Sin versión del modelo de la Champions") from e


def europe_results(out: dict) -> list[data.Match]:
    return [data.Match(UCL, out["season"], date.fromisoformat(d), h, a, hg, ag)
            for d, h, a, hg, ag in out["results"]]


def cycle(now: datetime, leagues: list[League], *, fetcher: Callable[[], None],
          builder: Callable[[League, date], dict], version: str, commit: str,
          store_path: Path = store.PATH, out_dir: Path = OUT_DIR,
          export: Callable[[], None] | None = None,
          europe_builder: Callable[[date], dict] | None = None,
          europe_version: str = "") -> dict:
    fetcher()                                                  # 1-2: todo o nada
    outs = {lg.code: builder(lg, now.date()) for lg in leagues}   # 3: en memoria
    ucl = europe_builder(now.date()) if europe_builder else None
    played = data.load_matches([lg.code for lg in leagues], [data.CURRENT_SEASON])
    new = predictions(outs, now, version, commit)
    if ucl is not None:
        new += predictions({UCL: ucl}, now, europe_version, commit)
        played += europe_results(ucl)
    old = store.load(store_path)
    rows, added = store.add_predictions(old, new)
    rows, filled = store.record_results(rows, results(played))
    store.check_append_only(old, rows)
    live = live_metrics(rows, now, ucl["base"] if ucl else None)
    for code, out in outs.items():                             # 4: recién ahora se escribe
        store.write_atomic(out_dir / f"clubs_{code}.json",
                           json.dumps(out, ensure_ascii=False, indent=1))
    if ucl is not None:
        store.write_atomic(out_dir / "ucl.json", json.dumps(ucl, ensure_ascii=False, indent=1))
    store.write_atomic(out_dir / LIVE.name, json.dumps(live, ensure_ascii=False, indent=1))
    store.save(rows, store_path)
    if export:
        export()
    return {"added": added, "filled": filled, "live": live}


def main() -> int:
    leagues = list(LEAGUES.values())
    now = datetime.now(timezone.utc)
    version, commit = model_version()
    from src.europe import run as europe_run
    from tools import export_frontend
    try:
        res = cycle(now, leagues, fetcher=lambda: fetch(sources(leagues) + europe_sources()),
                    builder=lambda lg, today: run.build(lg, today=today),
                    version=version, commit=commit, export=export_frontend.main,
                    europe_builder=lambda today: europe_run.build(today),
                    europe_version=europe_version())
    except SourceError as e:
        print(f"❌ Fuente caída, no se modificó nada: {e}", file=sys.stderr)
        return 2
    live = res["live"]
    print(f"✅ {res['added']} predicciones nuevas (modelo {version}), {res['filled']} "
          f"resultados registrados; {live['all']['n']} partidos evaluados, "
          f"{live['n_pending']} pendientes; Champions: {live['ucl']['n']} evaluados, "
          f"{live['ucl']['n_pending']} pendientes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
