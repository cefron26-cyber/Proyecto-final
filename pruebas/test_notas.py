import json

import notas as NT

LISTA = {"001": "Ana", "002": "Beto", "003": "Caro"}


def hoja(archivo, codigo, aciertos=10, **extra):
    return {"archivo": archivo, "codigo": codigo, "aciertos": aciertos,
            "total": 20, "fecha": "2026-11-07", **extra}


def test_estado_hoja():
    assert NT.estado_hoja({"codigo": "ERROR"}, set(), LISTA) == "error"
    assert NT.estado_hoja({"codigo": "00?"}, set(), LISTA) == "ilegible"
    assert NT.estado_hoja({"codigo": "001"}, {"001"}, LISTA) == "repetido"
    assert NT.estado_hoja({"codigo": "099"}, set(), LISTA) == "fuera"
    assert NT.estado_hoja({"codigo": "099"}, set(), {}) == "ok"   # aún sin lista
    assert NT.estado_hoja({"codigo": "002"}, set(), LISTA) == "ok"


def test_ordenar_revisar_arriba_y_por_codigo():
    hojas = [hoja("a", "003"), hoja("b", "???"), hoja("c", "001"), hoja("d", "099")]
    orden = [h["archivo"] for h in NT.ordenar(hojas, set(), LISTA)]
    assert orden == ["b", "d", "c", "a"]


def test_fusionar_reemplaza_al_mismo_alumno_y_conserva_campos():
    guardados = [hoja("viejo.jpg", "001", 5, imagen="v.jpg", codigo_corregido=True),
                 hoja("otro.jpg", "002")]
    nuevos = [hoja("nuevo.jpg", "001", 18, foto_borrada=True)]
    registros, reemplazos = NT.fusionar(guardados, nuevos, LISTA)
    por_archivo = {r["archivo"]: r for r in registros}
    assert set(por_archivo) == {"otro.jpg", "nuevo.jpg"}
    assert por_archivo["nuevo.jpg"]["foto_borrada"] is True   # no se pierden campos
    assert [(v["archivo"], n["archivo"]) for v, n in reemplazos] == [("viejo.jpg", "nuevo.jpg")]


def test_codigo_dudoso_o_fuera_de_lista_no_pisa_a_nadie():
    guardados = [hoja("a.jpg", "001"), hoja("b.jpg", "099")]
    nuevos = [hoja("c.jpg", "00?"), hoja("d.jpg", "099")]
    registros, reemplazos = NT.fusionar(guardados, nuevos, LISTA)
    assert reemplazos == []
    assert {r["archivo"] for r in registros} == {"a.jpg", "b.jpg", "c.jpg", "d.jpg"}


def test_misma_foto_otra_vez_se_actualiza_sin_reemplazo():
    registros, reemplazos = NT.fusionar([hoja("a.jpg", "001", 5)],
                                        [hoja("a.jpg", "001", 7)], LISTA)
    assert reemplazos == [] and registros == [hoja("a.jpg", "001", 7)]


def test_dos_fotos_del_mismo_alumno_en_la_tanda_queda_la_ultima():
    registros, reemplazos = NT.fusionar([], [hoja("1.jpg", "002"), hoja("2.jpg", "002")], LISTA)
    assert [r["archivo"] for r in registros] == ["2.jpg"]
    assert len(reemplazos) == 1


def test_lo_que_anuncia_la_galeria_es_lo_que_se_guarda():
    guardados = [hoja("g.jpg", "001")]
    tanda = [hoja("t1.jpg", "002"), hoja("t2.jpg", "001"), hoja("t3.jpg", "002"),
             hoja("t4.jpg", "003")]
    estados = [NT.estado_en_tanda(tanda, i, set(), guardados, LISTA) for i in range(4)]
    assert estados == ["tapada", "reemplaza", "ok", "ok"]
    # Si se descarta la última foto de 002, la primera ya no queda tapada
    assert NT.estado_en_tanda(tanda, 0, {2}, guardados, LISTA) == "ok"
    _, reemplazos = NT.fusionar(guardados, tanda, LISTA)
    assert {v["archivo"] for v, _ in reemplazos} == {"g.jpg", "t1.jpg"}


def test_anotar_reemplazos(tmp_path):
    log = tmp_path / "reemplazos_x.log"
    NT.anotar_reemplazos(log, [(hoja("v.jpg", "001", 5), hoja("n.jpg", "001", 18))],
                         ahora="2026-11-07T10:00:00")
    linea = json.loads(log.read_text(encoding="utf-8").strip())
    assert linea["codigo"] == "001"
    assert linea["anterior"]["aciertos"] == 5 and linea["nueva"]["aciertos"] == 18
    NT.anotar_reemplazos(log, [])       # sin reemplazos no escribe nada
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1
