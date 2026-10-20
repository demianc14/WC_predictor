"""Tests del ETL y del modelo de probabilidad."""
from src.etl.pipeline import compute_posterior, extract, transform, validate_rows


def test_extract_carga_48_equipos():
    df = extract()
    assert len(df) == 48
    assert df["group"].nunique() == 12


def test_pipeline_validacion_y_transformacion():
    teams = validate_rows(extract())
    strengths = transform(teams)
    assert len(strengths) == 48
    for s in strengths:
        assert 0.0 <= s.prior <= 1.0
        assert 0.0 <= s.likelihood <= 1.0
        assert 0.0 <= s.posterior <= 1.0


def test_jerarquia_de_fuerzas_es_sensata():
    """España (rank 1, campeón vigente de la Euro) debe superar a Haití."""
    strengths = {s.fifa_code: s for s in transform(validate_rows(extract()))}
    assert strengths["ESP"].posterior > strengths["HAI"].posterior
    assert strengths["ARG"].posterior > strengths["NZL"].posterior
    assert strengths["BRA"].posterior > strengths["CUW"].posterior


def test_att_def_normalizados_al_promedio():
    """El promedio de att y defe del torneo debe ser 1.0 (definición de Maher)."""
    strengths = transform(validate_rows(extract()))
    avg_att = sum(s.att for s in strengths) / len(strengths)
    avg_def = sum(s.defe for s in strengths) / len(strengths)
    assert abs(avg_att - 1.0) < 0.01
    assert abs(avg_def - 1.0) < 0.01
    # España debe tener mejor perfil que Haití en ambas puntas
    d = {s.fifa_code: s for s in strengths}
    assert d["ESP"].att > d["HAI"].att
    assert d["ESP"].defe < d["HAI"].defe   # menor = mejor defensa


def test_posterior_renormaliza_pesos():
    # prior=1, likelihood=1 -> posterior=(0.2+0.5)/0.7 = 1.0
    assert abs(compute_posterior(1.0, 1.0) - 1.0) < 1e-9
    assert compute_posterior(0.0, 0.0) == 0.0
