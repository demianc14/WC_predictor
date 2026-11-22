"""Auditoría del almacén contra su historial de git.

    python -m src.pipeline.audit               # todo el historial de main
    python -m src.pipeline.audit --worktree    # más el archivo sin commitear (ciclo diario)

`store.save` compara contra el archivo en disco: una edición a mano seguida de un `save`
pasa sin error. Esta auditoría recorre cada commit que tocó el almacén, en el orden de la
rama (`--first-parent`), y exige `store.check_append_only` entre cada versión y la anterior.
Una reescritura que después se deshace igual queda registrada, porque el commit intermedio
existió.

Límite: audita la historia que git tiene en este clon. Una reescritura del propio historial
(force-push) no se ve desde aquí. En un clon superficial solo audita lo que hay, y avisa.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from src.pipeline import store


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def is_shallow(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--is-shallow-repository").strip() == "true"


def versions(repo: Path, rel: Path) -> list[tuple[str, str | None]]:
    """(commit, texto) de cada commit de la rama que tocó `rel`; None si ahí no existe."""
    out: list[tuple[str, str | None]] = []
    log = _git(repo, "log", "--first-parent", "--reverse", "--format=%H", "--", rel.as_posix())
    for commit in log.split():
        try:
            text: str | None = _git(repo, "show", f"{commit}:{rel.as_posix()}")
        except subprocess.CalledProcessError:
            text = None
        out.append((commit, text))
    return out


def audit(repo: Path = Path("."), rel: Path = store.PATH, worktree: bool = False) -> int:
    """Número de versiones auditadas. `StoreError` con el commit si alguna rompe la regla."""
    seq = versions(repo, rel)
    if worktree:
        path = repo / rel
        seq.append(("(sin commitear)", path.read_text(encoding="utf-8")
                    if path.exists() else None))
    prev: list[dict] = []
    for commit, text in seq:
        where = commit if commit.startswith("(") else commit[:12]
        if text is None:
            raise store.StoreError(f"{where}: el almacén no existe en esta versión")
        rows = store.parse(text, f"{rel} en {where}")
        try:
            store.check_append_only(prev, rows)
        except store.StoreError as e:
            raise store.StoreError(f"{where}: {e}") from e
        prev = rows
    return len(seq)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audita el historial de git del almacén")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--worktree", action="store_true",
                    help="incluye el archivo sin commitear como última versión")
    args = ap.parse_args(argv)
    try:
        if is_shallow(args.repo):
            print("⚠️  clon superficial: solo se audita la historia disponible", file=sys.stderr)
        n = audit(args.repo, store.PATH, args.worktree)
    except store.StoreError as e:
        print(f"❌ El almacén no es solo-para-agregar: {e}", file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"❌ No se pudo leer el historial de git: {e}", file=sys.stderr)
        return 2
    print(f"✅ {n} versiones del almacén auditadas: solo se agregó y se completaron resultados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
