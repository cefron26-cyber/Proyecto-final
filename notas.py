# -*- coding: utf-8 -*-
"""Reglas de las notas de un examen (sin interfaz: se puede probar sin Kivy).

Una "hoja" es el dict que deja ``lector_omr.calificar_foto``:
    {archivo, codigo, aciertos, total, respuestas, fecha, imagen, ...}
Las hojas se manejan como dicts tal cual (nunca se reconstruyen con campos
fijos), para no perder datos como ``codigo_corregido`` o ``foto_borrada``.

``lista`` es ``{código: nombre}`` de la lista del curso ({} si aún no hay).
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

log = logging.getLogger("calificador.notas")


def estado_hoja(r: dict, repetidos, lista) -> str:
    """'error', 'ilegible', 'repetido', 'fuera' (no está en la lista) u 'ok'."""
    codigo = str(r.get("codigo", "???"))
    if codigo == "ERROR":
        return "error"
    if not codigo.isdigit():
        return "ilegible"
    if codigo in repetidos:
        return "repetido"
    if lista and codigo not in lista:
        return "fuera"
    return "ok"


def ordenar(notas: list[dict], repetidos, lista) -> list[dict]:
    """Por código (001, 002…); las que hay que revisar, arriba.
    sorted es estable: entre hojas iguales se mantiene el orden de llegada."""
    def clave(r):
        cod = str(r.get("codigo", ""))
        return (estado_hoja(r, repetidos, lista) == "ok",
                int(cod) if cod.isdigit() else -1, r.get("fecha", ""))
    return sorted(notas, key=clave)


def puede_reemplazar(codigo, lista) -> bool:
    """Solo un código legible y de la lista (o cualquiera legible si aún no
    hay lista) puede reemplazar la hoja anterior del mismo alumno. Un código
    dudoso no pisa a nadie y queda 'por revisar'."""
    cod = str(codigo or "")
    return cod.isdigit() and (not lista or cod in lista)


def estado_en_tanda(hojas: list[dict], i: int, descartadas, guardados: list[dict],
                    lista) -> str:
    """Estado de la hoja i de una tanda recién calificada (antes de guardar).

    Además de los de ``estado_hoja``:
      'tapada'    → hay otra foto del mismo alumno más adelante en la tanda
                    (se guardará esa).
      'reemplaza' → ya había una nota guardada de ese alumno.
    Debe coincidir con lo que hace ``fusionar`` al guardar."""
    r = hojas[i]
    estado = estado_hoja(r, set(), lista)
    if estado != "ok":
        return estado
    cod = str(r.get("codigo"))
    if any(j > i and j not in descartadas and str(o.get("codigo")) == cod
           for j, o in enumerate(hojas)):
        return "tapada"
    if any(str(g.get("codigo")) == cod for g in guardados):
        return "reemplaza"
    return "ok"


def fusionar(guardados: list[dict], nuevos: list[dict], lista):
    """Agrega/actualiza hojas (clave: archivo). Si llega otra hoja del mismo
    alumno se queda la última y la anterior sale.

    Devuelve ``(registros, reemplazos)``: la lista a guardar y los pares
    ``(hoja_que_sale, hoja_que_queda)``. No toca disco."""
    registros = {r.get("archivo", ""): r for r in guardados}
    reemplazos = []
    for r in nuevos:
        if puede_reemplazar(r.get("codigo", ""), lista):
            cod = str(r.get("codigo", ""))
            for archivo, viejo in list(registros.items()):
                if archivo != r["archivo"] and str(viejo.get("codigo", "")) == cod:
                    del registros[archivo]
                    reemplazos.append((viejo, r))
        registros[r["archivo"]] = r
    return list(registros.values()), reemplazos


def anotar_reemplazos(ruta_log, reemplazos, ahora=None) -> None:
    """Agrega al historial (una línea JSON por reemplazo) qué nota había y
    cuál quedó. Un fallo al anotar no impide guardar las notas."""
    if not reemplazos:
        return
    ahora = ahora or datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with open(Path(ruta_log), "a", encoding="utf-8") as f:
            for viejo, nuevo in reemplazos:
                f.write(json.dumps({
                    "fecha": ahora, "codigo": nuevo.get("codigo"),
                    "anterior": {k: viejo.get(k) for k in
                                 ("archivo", "aciertos", "total", "fecha", "respuestas")},
                    "nueva": {k: nuevo.get(k) for k in
                              ("archivo", "aciertos", "total", "fecha")},
                }, ensure_ascii=False) + "\n")
    except OSError:
        log.exception("No se pudo anotar el historial de reemplazos")
