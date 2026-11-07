# -*- coding: utf-8 -*-
"""Sube el .json.enc al coordinador vía Apps Script (Web App). Solo stdlib.

No usa OAuth ni librerías externas (nada que tocar en buildozer): autentica con
un token compartido y manda el archivo (en base64) por HTTP POST. El Apps Script
lo enruta a ``Área/Año/`` en Google Drive.
"""
from __future__ import annotations
import base64
import json
import os
import urllib.request
import urllib.error

# La URL del Apps Script y el token YA NO están en el código: vienen de
# credenciales.py (archivo en la carpeta privada de la app).


def subir_a_drive(ruta_archivo, area, periodo, url_script, token, timeout=20):
    """Sube el archivo al Apps Script. Devuelve ``(ok: bool, mensaje: str)``."""
    if not url_script or not url_script.endswith("/exec"):
        return False, "Falta configurar la dirección del envío al coordinador."
    if not token:
        return False, "Falta configurar el token del envío al coordinador."
    if not os.path.exists(ruta_archivo):
        return False, "El archivo no existe en el teléfono."
    try:
        with open(ruta_archivo, "rb") as f:
            contenido_b64 = base64.b64encode(f.read()).decode("utf-8")
        payload = {
            "token": token,
            "filename": os.path.basename(ruta_archivo),
            "content": contenido_b64,
            "area": area,
            "anio": str(periodo).split("-")[0],   # "2026-1" -> "2026"
        }
        datos = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url_script, data=datos,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            cruda = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError:
        return False, "Sin internet o el servidor no responde."
    except Exception as e:  # noqa: BLE001 — cualquier fallo de red/IO
        return False, str(e)

    try:
        r = json.loads(cruda)
    except ValueError:
        return False, ("Respuesta inesperada del servidor. Revisa que la "
                       "implementación sea 'Cualquiera' y que la URL termine "
                       "en /exec.")
    if r.get("status") == "success":
        return True, "ok"
    return False, r.get("message", "Error desconocido del servidor.")
