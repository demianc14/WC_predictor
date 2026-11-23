"""Cada ADR de docs/adr/ tiene sus cuatro secciones con texto y está enlazado desde el README."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
SECCIONES = ("Contexto", "Decisión", "Alternativa descartada", "Consecuencia")
MINIMO = 7


def _adrs() -> list[Path]:
    if not (ROOT / "docs").is_dir():
        pytest.skip("imagen Docker: .dockerignore deja fuera docs/")
    return sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_cada_adr_tiene_las_cuatro_secciones_con_texto():
    adrs = _adrs()
    assert len(adrs) >= MINIMO, f"se esperaban al menos {MINIMO} ADR en docs/adr/, hay {len(adrs)}"
    for adr in adrs:
        texto = adr.read_text(encoding="utf-8")
        partes = re.split(r"^## +(.+?)\s*$", texto, flags=re.M)
        cuerpos = dict(zip(partes[1::2], partes[2::2]))
        for seccion in SECCIONES:
            assert seccion in cuerpos, f"{adr.name}: falta la sección «{seccion}»"
            assert cuerpos[seccion].strip(), f"{adr.name}: la sección «{seccion}» está vacía"


def test_cada_adr_esta_enlazado_desde_el_readme():
    adrs = _adrs()
    assert adrs, "no hay ADR en docs/adr/"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    enlaces = set(re.findall(r"\]\(([^)\s#]+)", readme))
    for adr in adrs:
        rel = adr.relative_to(ROOT).as_posix()
        assert rel in enlaces, f"README.md no enlaza {rel}"
