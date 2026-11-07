# -*- coding: utf-8 -*-
"""Lectura y escritura SEGURA de los JSON de la app (notas y claves).

- Escritura atómica: se escribe a ``archivo.tmp`` y se cambia de nombre con
  ``os.replace``. Si la app se cierra o se va la luz a mitad de camino, el
  archivo anterior queda intacto (nunca queda medio escrito).
- Copias rotativas: antes de cada escritura, la versión anterior (si es un
  JSON válido) se guarda como ``archivo.bak1`` … ``archivo.bak5``
  (bak1 = la más reciente).
- Lectura con recuperación: si el archivo está dañado, NO se devuelve una
  lista vacía en silencio. El dañado se aparta como ``archivo.danado-<fecha>``
  (no se borra nunca) y se recupera la copia válida más reciente.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger("calificador.almacen")

COPIAS = 5


def _bak(ruta: Path, i: int) -> Path:
    return ruta.with_name(f"{ruta.name}.bak{i}")


def _es_json_valido(ruta: Path) -> bool:
    try:
        json.loads(ruta.read_text(encoding="utf-8"))
        return True
    except (OSError, ValueError, UnicodeDecodeError):
        return False


def _rotar(ruta: Path, copias: int) -> None:
    """ruta → bak1, bak1 → bak2, … (la más vieja se descarta)."""
    if not ruta.exists() or not _es_json_valido(ruta):
        return
    for i in range(copias - 1, 0, -1):
        if _bak(ruta, i).exists():
            os.replace(_bak(ruta, i), _bak(ruta, i + 1))
    shutil.copy2(ruta, _bak(ruta, 1))


def escribir(ruta, datos, indent: int = 2, copias: int = COPIAS) -> None:
    """Guarda ``datos`` como JSON de forma atómica, con copia de la versión
    anterior. Lanza la excepción si no se pudo guardar (no la oculta)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(datos, indent=indent, ensure_ascii=False)
    tmp = ruta.with_name(ruta.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    if copias:
        try:
            _rotar(ruta, copias)
        except OSError:
            # Sin copia no se pierde nada de lo nuevo: se sigue guardando
            log.exception("No se pudo hacer la copia de %s", ruta)
    os.replace(tmp, ruta)


class JsonDanado(Exception):
    """El archivo existe pero no se puede leer como JSON."""

    def __init__(self, ruta: Path, causa: Exception):
        super().__init__(f"{ruta.name} está dañado: {causa}")
        self.ruta = ruta
        self.causa = causa


def leer(ruta, por_defecto=None):
    """Lee un JSON. Si no existe devuelve ``por_defecto``; si está dañado
    lanza ``JsonDanado`` (nunca devuelve ``por_defecto`` en silencio)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return por_defecto
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        log.error("JSON dañado: %s (%s)", ruta, e)
        raise JsonDanado(ruta, e) from e


def leer_con_recuperacion(ruta, por_defecto=None):
    """Como ``leer``, pero si el archivo está dañado lo aparta y recupera la
    copia válida más reciente.

    Devuelve ``(datos, aviso)``: ``aviso`` es None si todo estuvo bien, o un
    texto para mostrarle al docente explicando qué pasó.
    """
    ruta = Path(ruta)
    try:
        return leer(ruta, por_defecto), None
    except JsonDanado as e:
        danado = ruta.with_name(f"{ruta.name}.danado-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(ruta, danado)
        except OSError:
            log.exception("No se pudo apartar %s", ruta)
            raise e
        for i in range(1, COPIAS + 1):
            copia = _bak(ruta, i)
            if copia.exists() and _es_json_valido(copia):
                shutil.copy2(copia, ruta)
                fecha = time.strftime("%d/%m/%Y %H:%M", time.localtime(copia.stat().st_mtime))
                log.warning("Recuperado %s desde %s", ruta, copia.name)
                return (json.loads(ruta.read_text(encoding="utf-8")),
                        f"El archivo '{ruta.name}' estaba dañado. Recuperamos la "
                        f"copia guardada el {fecha}; revisa si falta alguna hoja "
                        f"calificada después de esa hora.\n\nEl archivo dañado "
                        f"quedó guardado como '{danado.name}'.")
        log.error("Sin copia válida para %s", ruta)
        return (por_defecto,
                f"El archivo '{ruta.name}' estaba dañado y no había una copia "
                f"para recuperarlo. No se borró: quedó guardado como "
                f"'{danado.name}' por si se puede reparar.")
