# -*- coding: utf-8 -*-
"""Credenciales para enviar notas al coordinador (fuera del código).

La llave de cifrado, el token del Apps Script y su URL ya NO viven en el
código ni en el APK: el docente los pega una vez (se los da coordinación) y
quedan en ``credenciales_coordinador.json`` dentro de la carpeta privada de
datos de la app (en Android, ``user_data_dir``: otras apps no pueden leerla).

Formato del archivo:
    {"url_script": "https://script.google.com/macros/s/.../exec",
     "token": "...",
     "llave": "..."}
"""
from __future__ import annotations

from pathlib import Path

import almacen_json as AJ

NOMBRE = "credenciales_coordinador.json"
CAMPOS = ("url_script", "token", "llave")
LARGO_MINIMO_LLAVE = 16
LARGO_MINIMO_TOKEN = 8


def ruta(carpeta_datos) -> Path:
    return Path(carpeta_datos) / NOMBRE


def cargar(carpeta_datos) -> dict:
    """Devuelve las credenciales guardadas ({} si no hay o están dañadas)."""
    try:
        d = AJ.leer(ruta(carpeta_datos), {})
    except AJ.JsonDanado:
        return {}
    return {k: str(d.get(k, "")).strip() for k in CAMPOS} if isinstance(d, dict) else {}


def problemas(d: dict) -> list[str]:
    """Lista de lo que falta o está mal (vacía si se puede enviar)."""
    errores = []
    url = d.get("url_script", "")
    if not (url.startswith("https://script.google.com/") and url.endswith("/exec")):
        errores.append("La dirección debe empezar por https://script.google.com/ "
                       "y terminar en /exec.")
    if len(d.get("token", "")) < LARGO_MINIMO_TOKEN:
        errores.append(f"El token debe tener al menos {LARGO_MINIMO_TOKEN} caracteres.")
    if len(d.get("llave", "")) < LARGO_MINIMO_LLAVE:
        errores.append(f"La llave debe tener al menos {LARGO_MINIMO_LLAVE} caracteres.")
    return errores


def guardar(carpeta_datos, d: dict) -> None:
    datos = {k: str(d.get(k, "")).strip() for k in CAMPOS}
    errores = problemas(datos)
    if errores:
        raise ValueError("\n".join(errores))
    AJ.escribir(ruta(carpeta_datos), datos, copias=0)
