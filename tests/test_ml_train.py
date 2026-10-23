"""Caché de features: su nombre depende de los datos y también del código."""
from src.ml import train


def test_el_hash_del_codigo_cambia_si_cambia_un_archivo(tmp_path, monkeypatch):
    a, b = tmp_path / "features.py", tmp_path / "model.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    monkeypatch.setattr(train, "FEATURE_CODE", (a, b))
    h = train.code_hash()
    assert train.code_hash() == h                          # estable si nada cambia
    b.write_text("y = 3\n")
    assert train.code_hash() != h


def test_el_hash_del_codigo_cubre_archivos_que_existen():
    assert all(p.exists() for p in train.FEATURE_CODE)
    assert len(train.code_hash()) == 8
