import json

import pytest

import almacen_json as AJ


def test_escritura_atomica_y_copias_rotativas(tmp_path):
    f = tmp_path / "notas_x.json"
    for i in range(AJ.COPIAS + 2):
        AJ.escribir(f, [{"i": i}])
    assert AJ.leer(f) == [{"i": AJ.COPIAS + 1}]
    assert json.loads((tmp_path / "notas_x.json.bak1").read_text()) == [{"i": AJ.COPIAS}]
    assert (tmp_path / f"notas_x.json.bak{AJ.COPIAS}").exists()
    assert not (tmp_path / f"notas_x.json.bak{AJ.COPIAS + 1}").exists()
    assert not (tmp_path / "notas_x.json.tmp").exists()


def test_no_existe_devuelve_por_defecto(tmp_path):
    assert AJ.leer(tmp_path / "nada.json", []) == []
    assert AJ.leer_con_recuperacion(tmp_path / "nada.json", []) == ([], None)


def test_danado_recupera_la_ultima_copia_buena(tmp_path):
    f = tmp_path / "notas_x.json"
    AJ.escribir(f, [{"i": 1}])
    AJ.escribir(f, [{"i": 2}])
    f.write_text('[{"i": 2', encoding="utf-8")       # corte a mitad
    datos, aviso = AJ.leer_con_recuperacion(f, [])
    assert datos == [{"i": 1}]
    assert aviso and "Recuperamos" in aviso
    assert list(tmp_path.glob("notas_x.json.danado-*"))  # el dañado no se borra


def test_danado_sin_copias_avisa_y_conserva(tmp_path):
    f = tmp_path / "otra.json"
    f.write_text("{malo", encoding="utf-8")
    datos, aviso = AJ.leer_con_recuperacion(f, [])
    assert datos == [] and "no había una copia" in aviso
    assert list(tmp_path.glob("otra.json.danado-*"))


def test_leer_danado_lanza_error(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{", encoding="utf-8")
    with pytest.raises(AJ.JsonDanado):
        AJ.leer(f, [])


def test_la_copia_nunca_guarda_un_json_danado(tmp_path):
    f = tmp_path / "x.json"
    AJ.escribir(f, [1])
    AJ.escribir(f, [2])                 # bak1 = [1]
    f.write_text("{", encoding="utf-8")
    AJ.escribir(f, [3])                 # el dañado NO desplaza las copias buenas
    assert json.loads((tmp_path / "x.json.bak1").read_text()) == [1]
    assert not (tmp_path / "x.json.bak2").exists()
    assert AJ.leer(f) == [3]
