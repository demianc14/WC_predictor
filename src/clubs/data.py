"""Partidos y cuotas de clubes desde football-data.co.uk.

Un CSV por liga y temporada (`mmz4281/{temporada}/{división}.csv`) con
resultado, xG (desde 2026-27), tiros y cuotas de apertura/cierre, más
`fixtures.csv` con la próxima jornada y sus cuotas. Las temporadas cerradas
se bajan una vez; la actual y el calendario se refrescan cada 12 horas.
"""
from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
CACHE_DIR = Path("data/cache/clubs")
TTL_SECONDS = 12 * 3600
CURRENT_SEASON = "2627"


@dataclass(frozen=True)
class Match:
    div: str
    season: str
    day: date
    home: str
    away: str
    hg: int | None = None          # None = partido por jugar
    ag: int | None = None
    hxg: float | None = None
    axg: float | None = None
    # 1X2: cuota de cierre promedio, o la promedio si todavía no hay cierre
    odds: tuple[float, float, float] | None = None

    @property
    def played(self) -> bool:
        return self.hg is not None

    def score(self) -> tuple[int, int]:
        """(goles local, goles visita) de un partido jugado; falla si no se jugó."""
        if self.hg is None or self.ag is None:
            raise ValueError(f"{self.home}-{self.away} ({self.day}) no se jugó")
        return self.hg, self.ag


def _fresh(path: Path, permanent: bool) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    return permanent or (time.time() - path.stat().st_mtime) < TTL_SECONDS


def _download(url: str, target: Path) -> None:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (WC_predictor)"})
    with urlopen(req, timeout=60) as resp:
        body = resp.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)


def ensure_season(div: str, season: str, force: bool = False) -> Path:
    path = CACHE_DIR / f"{div}_{season}.csv"
    if force or not _fresh(path, permanent=season != CURRENT_SEASON):
        _download(BASE_URL.format(season=season, div=div), path)
    return path


def ensure_fixtures(force: bool = False) -> Path:
    path = CACHE_DIR / "fixtures.csv"
    if force or not _fresh(path, permanent=False):
        _download(FIXTURES_URL, path)
    return path


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _odds(r: dict) -> tuple[float, float, float] | None:
    for keys in (("AvgCH", "AvgCD", "AvgCA"), ("AvgH", "AvgD", "AvgA"),
                 ("B365H", "B365D", "B365A")):
        vals = [_num(r.get(k)) for k in keys]
        if all(v and v > 1 for v in vals):
            return tuple(vals)  # type: ignore[return-value]
    return None


def parse_csv(text: str, season: str) -> list[Match]:
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        if not r.get("HomeTeam") or not r.get("Date"):
            continue
        fmt = "%d/%m/%Y" if len(r["Date"].split("/")[-1]) == 4 else "%d/%m/%y"
        hg, ag = _num(r.get("FTHG")), _num(r.get("FTAG"))
        out.append(Match(
            div=r["Div"], season=season, day=datetime.strptime(r["Date"], fmt).date(),
            home=r["HomeTeam"].strip(), away=r["AwayTeam"].strip(),
            hg=int(hg) if hg is not None else None, ag=int(ag) if ag is not None else None,
            hxg=_num(r.get("HxG")), axg=_num(r.get("AxG")), odds=_odds(r),
        ))
    return out


def load_matches(divs: list[str], seasons: list[str]) -> list[Match]:
    out: list[Match] = []
    for s in seasons:
        for d in divs:
            text = ensure_season(d, s).read_text(encoding="utf-8-sig", errors="replace")
            out += parse_csv(text, s)
    return sorted(out, key=lambda m: m.day)


def load_fixtures(div: str) -> list[Match]:
    text = ensure_fixtures().read_text(encoding="utf-8-sig", errors="replace")
    return [m for m in parse_csv(text, CURRENT_SEASON) if m.div == div and not m.played]
