"""Tests de los scrapers (lo que no depende de red)."""
from src.etl.scrapers.elo import FIFA_TO_ELO, parse_world_tsv


def test_mapeo_cubre_los_48_codes():
    # Los 48 FIFA codes del torneo deben tener mapeo a eloratings.
    assert len(FIFA_TO_ELO) == 48
    # Casos historicos que rompen ISO-2: Scotland=SQ (no SC), England=EN (no GB).
    assert FIFA_TO_ELO["SCO"] == "SQ"
    assert FIFA_TO_ELO["ENG"] == "EN"
    assert FIFA_TO_ELO["GER"] == "DE"
    assert FIFA_TO_ELO["ALG"] == "DZ"


def test_parse_world_tsv_extrae_codigo_y_elo():
    sample = (
        "1\t1\tES\t2129\t1\t2189\textras_ignorados\n"
        "2\t2\tAR\t2115\t1\t2172\n"
        "linea_basura_sin_tabs\n"
        "3\t3\tFR\tno_es_int\n"   # debe ignorarse
        "4\t4\tBR\t1978\n"
    )
    result = parse_world_tsv(sample)
    assert result == {"ES": 2129, "AR": 2115, "BR": 1978}
