import json

import pytest

import lector_omr as L


def clave(tmp_path, **cambios):
    base = {"examen": "t", "total_preguntas": 3, "clave_correctas": ["A", "B", "C"]}
    p = tmp_path / "respuestas_t.json"
    p.write_text(json.dumps({**base, **cambios}), encoding="utf-8")
    return p


def test_clave_valida(tmp_path):
    d = L.cargar_datos_examen(clave(tmp_path))
    assert d.total_preguntas == 3 and d.clave == {1: "A", 2: "B", 3: "C"}


@pytest.mark.parametrize("malo", [
    {"total_preguntas": 0, "clave_correctas": []},
    {"total_preguntas": 5},
    {"total_preguntas": "x"},
    {"total_preguntas": 99, "clave_correctas": ["A"] * 99},
])
def test_clave_invalida_se_rechaza_antes_de_calificar(tmp_path, malo):
    with pytest.raises(ValueError):
        L.cargar_datos_examen(clave(tmp_path, **malo))


def test_nota_con_total_cero_no_divide_por_cero():
    assert L._calcular_nota(0, 0) == L.NOTA_MIN
