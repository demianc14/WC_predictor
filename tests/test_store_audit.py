"""El historial de git del almacén cumple la regla solo-para-agregar, commit por commit.

`store.save` compara contra el archivo en disco, así que una edición a mano seguida de un
`save` pasa. Esta auditoría compara cada versión commiteada con la anterior.
Los repos de estos tests son temporales y locales, con datos ficticios.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from src.pipeline import audit, store

ROOT = Path(__file__).resolve().parent.parent
REL = Path("data/predictions/predicciones.csv")


@pytest.fixture(autouse=True)
def _con_git():
    """La imagen Docker no trae git (ni .git): ahí se saltan. En CI fuera de Docker, no."""
    if shutil.which("git") is None:
        if os.environ.get("CI") == "true":
            pytest.fail("CI sin git: la auditoría del almacén no se puede probar")
        pytest.skip("sin git en PATH (imagen Docker)")


def _row(mid: str, p1: str = "0.5000", result: str = "") -> dict:
    return {"match_id": mid, "league": "E0", "season": "2627", "match_date": "2026-10-24",
            "home": mid[-3], "away": mid[-1], "model": "dixon-coles", "model_version": "v1",
            "commit": "abc", "predicted_at": "2026-10-21T05:30:00Z",
            "p1": p1, "px": "0.2500", "p2": f"{0.75 - float(p1):.4f}",
            "result": result, "hg": "1" if result else "", "ag": "0" if result else "",
            "mk1": "", "mkx": "", "mk2": ""}


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-21T06:00:00Z",
           "GIT_COMMITTER_DATE": "2026-10-21T06:00:00Z"}
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=test",
                           "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                           *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def _commit(repo: Path, rows: list[dict], msg: str) -> str:
    (repo / REL).parent.mkdir(parents=True, exist_ok=True)
    (repo / REL).write_text(store.render(rows), encoding="utf-8")
    _git(repo, "add", str(REL))
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, [_row("E0-2627-A-B")], "primera predicción")
    _commit(tmp_path, [_row("E0-2627-A-B", result="H"), _row("E0-2627-C-D")],
            "resultado y otra predicción")
    return tmp_path


def test_un_historial_sano_pasa(repo):
    assert audit.audit(repo, REL) == 2


def test_cambiar_una_prediccion_commiteada_falla_y_nombra_el_commit(repo):
    bad = _commit(repo, [_row("E0-2627-A-B", p1="0.9000", result="H"), _row("E0-2627-C-D")],
                  "reescritura a mano")
    with pytest.raises(store.StoreError, match=bad[:7]) as e:
        audit.audit(repo, REL)
    assert "p1" in str(e.value)


def test_borrar_una_fila_commiteada_falla(repo):
    _commit(repo, [_row("E0-2627-A-B", result="H")], "se borra C-D")
    with pytest.raises(store.StoreError, match="borraría"):
        audit.audit(repo, REL)


def test_cambiar_un_resultado_commiteado_falla(repo):
    _commit(repo, [_row("E0-2627-A-B", result="A"), _row("E0-2627-C-D")], "otro resultado")
    with pytest.raises(store.StoreError, match="resultado"):
        audit.audit(repo, REL)


def test_una_reescritura_corregida_en_el_commit_siguiente_igual_queda_registrada(repo):
    """Volver al valor original no borra la violación: el commit intermedio existió."""
    _commit(repo, [_row("E0-2627-A-B", p1="0.9000", result="H"), _row("E0-2627-C-D")], "mal")
    _commit(repo, [_row("E0-2627-A-B", result="H"), _row("E0-2627-C-D")], "se deshace")
    with pytest.raises(store.StoreError):
        audit.audit(repo, REL)


def test_borrar_el_almacen_en_un_commit_falla(repo):
    _git(repo, "rm", "-q", str(REL))
    _git(repo, "commit", "-q", "-m", "se borra el almacén")
    with pytest.raises(store.StoreError, match="no existe"):
        audit.audit(repo, REL)


def test_worktree_audita_lo_que_todavia_no_se_commitea(repo):
    """El ciclo diario corre esto antes de commitear: el bot no pasa por CI."""
    assert audit.audit(repo, REL, worktree=True) == 3
    (repo / REL).write_text(store.render([_row("E0-2627-A-B", p1="0.1000", result="H"),
                                          _row("E0-2627-C-D")]), encoding="utf-8")
    assert audit.audit(repo, REL) == 2                      # lo commiteado sigue sano
    with pytest.raises(store.StoreError, match="sin commitear"):
        audit.audit(repo, REL, worktree=True)


def test_main_devuelve_1_si_hay_violacion(repo, capsys):
    assert audit.main(["--repo", str(repo)]) == 0
    _commit(repo, [_row("E0-2627-A-B", p1="0.9000", result="H"), _row("E0-2627-C-D")], "mal")
    assert audit.main(["--repo", str(repo)]) == 1
    assert "p1" in capsys.readouterr().err


def test_el_historial_real_del_almacen_es_solo_para_agregar():
    """El historial completo de este repo. En CI tiene que estar entero (fetch-depth: 0)."""
    if not (ROOT / ".git").exists():
        pytest.skip("imagen Docker: sin .git")
    if audit.is_shallow(ROOT):
        if os.environ.get("CI") == "true":
            pytest.fail("clon superficial en CI: ci.yml necesita fetch-depth: 0")
        pytest.skip("clon superficial: no hay historial que auditar")
    assert audit.audit(ROOT, REL) > 1


def test_los_workflows_corren_la_auditoria():
    if not (ROOT / ".github").is_dir():
        pytest.skip("imagen Docker: .dockerignore deja fuera .github/")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci
    paso, commit = daily.find("python -m src.pipeline.audit --worktree"), daily.find("git commit")
    assert 0 <= paso < commit                               # antes de commitear
