"""Almacén de predicciones: un CSV versionado en el repo, solo para agregar.

Una fila por (partido, versión del modelo). Regla central: una predicción ya
guardada NUNCA se sobrescribe. Si el modelo cambia, entra otra fila con otra
versión. Lo único que se completa después es el resultado y las cuotas de
cierre, y solo si estaban vacíos. `save` verifica la regla contra lo que hay
en disco antes de escribir, y escribe con un reemplazo atómico.

El historial de git del archivo es la prueba pública de que cada predicción
existía antes del partido.
"""
from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

PATH = Path("data/predictions/predicciones.csv")
COLUMNS = ["match_id", "league", "season", "match_date", "home", "away",
           "model", "model_version", "commit", "predicted_at", "p1", "px", "p2",
           "result", "hg", "ag", "mk1", "mkx", "mk2"]
PREDICTION = COLUMNS[:13]          # inmutables una vez escritas
OUTCOME = ["result", "hg", "ag", "mk1", "mkx", "mk2"]


class StoreError(RuntimeError):
    pass


def match_id(div: str, season: str, home: str, away: str) -> str:
    """Estable aunque el partido se reprograme: en una liga cada cruce local-visita es único."""
    return f"{div}-{season}-{home}-{away}".replace(" ", "_")


def key(row: dict) -> tuple[str, str]:
    return row["match_id"], row["model_version"]


def load(path: Path = PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if rows and list(rows[0]) != COLUMNS:
        raise StoreError(f"Columnas inesperadas en {path}: {list(rows[0])}")
    return rows


def add_predictions(rows: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    """Agrega las que no existen para esa versión; las existentes no se tocan."""
    have = {key(r) for r in rows}
    out, added = [dict(r) for r in rows], 0
    for n in new:
        if key(n) in have:
            continue
        out.append({c: n.get(c, "") for c in COLUMNS})
        have.add(key(n))
        added += 1
    return out, added


def record_results(rows: list[dict], results: dict[str, dict]) -> tuple[list[dict], int]:
    """Completa resultado y cierre por match_id. Un resultado distinto al guardado es error."""
    out, filled = [], 0
    for r in rows:
        r = dict(r)
        res = results.get(r["match_id"])
        if res:
            if r["result"] and (r["result"], r["hg"], r["ag"]) != (
                    res["result"], str(res["hg"]), str(res["ag"])):
                raise StoreError(f"{r['match_id']}: el resultado guardado {r['result']} "
                                 f"{r['hg']}-{r['ag']} no coincide con {res}")
            if not r["result"]:
                r.update({c: str(res.get(c, "")) for c in OUTCOME})
                filled += 1
            elif not r["mk1"] and res.get("mk1") not in (None, ""):
                r.update({c: str(res[c]) for c in ("mk1", "mkx", "mk2")})
        out.append(r)
    return out, filled


def check_append_only(old: list[dict], new: list[dict]) -> None:
    """Todo lo viejo sigue, con la predicción idéntica y sin perder resultados."""
    by_key = {key(r): r for r in new}
    for r in old:
        n = by_key.get(key(r))
        if n is None:
            raise StoreError(f"Se borraría la predicción {key(r)}")
        changed = [c for c in PREDICTION if str(r[c]) != str(n[c])]
        if changed:
            raise StoreError(f"Se sobrescribiría {key(r)}: {changed}")
        lost = [c for c in OUTCOME if r[c] and str(r[c]) != str(n[c])]
        if lost:
            raise StoreError(f"Se cambiaría el resultado de {key(r)}: {lost}")


def render(rows: list[dict]) -> str:
    rows = sorted(rows, key=lambda r: (r["match_date"], r["league"], r["home"],
                                       r["predicted_at"]))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def write_atomic(path: Path, text: str) -> None:
    """Escribe en un temporal del mismo directorio y lo reemplaza de una vez."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(rows: list[dict], path: Path = PATH) -> None:
    check_append_only(load(path), rows)
    write_atomic(path, render(rows))
