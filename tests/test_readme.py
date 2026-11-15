"""La portada no miente: el número de tests y los enlaces relativos se verifican."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "docs" / "archivo-mundial.md"]


def _collected() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, out[-300:]
    return int(m.group(1))


def test_el_numero_de_tests_del_readme_coincide_con_pytest():
    texto = (ROOT / "README.md").read_text(encoding="utf-8")
    citados = {int(n) for n in re.findall(r"\b(\d+) tests\b", texto)}
    assert citados, "el README ya no cita el número de tests"
    assert citados == {_collected()}


def test_los_enlaces_relativos_existen():
    if not (ROOT / "docs").is_dir():
        pytest.skip("imagen Docker: .dockerignore deja fuera docs/ y data/")
    for doc in DOCS:
        assert doc.exists(), doc
        texto = doc.read_text(encoding="utf-8")
        for destino in re.findall(r"\]\(([^)\s]+)\)", texto):
            if re.match(r"[a-z]+:", destino) or destino.startswith("#"):
                continue
            ruta = (doc.parent / destino.split("#")[0]).resolve()
            assert ruta.exists(), f"{doc.name}: enlace roto → {destino}"
