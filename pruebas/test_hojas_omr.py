"""Las 20 hojas de prueba se leen exactamente como se diseñaron.

Misma comparación que verificar_pruebas.py, pero sin reescribir las imágenes
ni el Excel de resultado_esperado (solo compara)."""
import pytest

import generar_pruebas as GP
import verificar_pruebas as VP

COMPARAR = ("codigo", "aciertos", "blanco", "doble", "dudosas", "tenues")


@pytest.mark.parametrize("caso", GP.CASOS, ids=lambda c: f"hoja{c['n']:02d}")
def test_hoja_se_lee_como_se_diseno(caso):
    foto = VP.AQUI / "fotos" / f"{GP.nombre_archivo(caso)}.jpg"
    if not foto.exists():
        pytest.skip("Faltan las fotos: corre pruebas/generar_pruebas.py")
    res, _ = VP.leer(foto)
    esp = VP.diseno(caso)
    assert esp["error"] == bool(res.get("error")), res
    if not esp["error"]:
        assert {k: res[k] for k in COMPARAR} == {k: esp[k] for k in COMPARAR}
