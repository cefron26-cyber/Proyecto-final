"""Cifrado ligero de los JSON (privacidad casual en Drive).

La llave ya NO está en el código: se pasa en cada llamada y viene de
``credenciales.py`` (archivo en la carpeta privada de la app). El formato
del archivo cifrado (LSE1) no cambia: la app del coordinador lo sigue
abriendo con la misma llave.
"""
from __future__ import annotations
import hashlib
import hmac
import os
from pathlib import Path

MAGIA = b"LSE1"
_TAM_SAL = 16
_TAM_HMAC = 32
_CABECERA = len(MAGIA) + _TAM_SAL


def _llave_bytes(llave) -> bytes:
    if isinstance(llave, str):
        llave = llave.encode("utf-8")
    if not llave:
        raise ValueError("Falta la llave de cifrado: configúrala con los datos "
                         "que te dio coordinación.")
    return llave


def _derivar(llave: bytes, etiqueta: bytes, sal: bytes) -> bytes:
    return hmac.new(llave, etiqueta + sal, hashlib.sha256).digest()

def _keystream(clave: bytes, sal: bytes, n: int) -> bytes:
    salida = bytearray()
    contador = 0
    while len(salida) < n:
        bloque = hmac.new(clave, sal + contador.to_bytes(8, "big"), hashlib.sha256).digest()
        salida.extend(bloque)
        contador += 1
    return bytes(salida[:n])

def esta_cifrado(blob: bytes) -> bool:
    return blob[: len(MAGIA)] == MAGIA

def cifrar(datos: bytes, llave) -> bytes:
    llave = _llave_bytes(llave)
    sal = os.urandom(_TAM_SAL)
    clave_cifrado = _derivar(llave, b"cifrado", sal)
    clave_mac = _derivar(llave, b"mac", sal)
    keystream = _keystream(clave_cifrado, sal, len(datos))
    cifrado = bytes(a ^ b for a, b in zip(datos, keystream))
    cuerpo = MAGIA + sal + cifrado
    firma = hmac.new(clave_mac, cuerpo, hashlib.sha256).digest()
    return cuerpo + firma

def descifrar(blob: bytes, llave) -> bytes:
    llave = _llave_bytes(llave)
    if not esta_cifrado(blob) or len(blob) < _CABECERA + _TAM_HMAC:
        raise ValueError("El contenido no está cifrado con este formato.")
    cuerpo, firma = blob[:-_TAM_HMAC], blob[-_TAM_HMAC:]
    sal = cuerpo[len(MAGIA) : _CABECERA]
    cifrado = cuerpo[_CABECERA:]
    clave_mac = _derivar(llave, b"mac", sal)
    if not hmac.compare_digest(firma, hmac.new(clave_mac, cuerpo, hashlib.sha256).digest()):
        raise ValueError("Integridad inválida: llave incorrecta o archivo alterado.")
    clave_cifrado = _derivar(llave, b"cifrado", sal)
    keystream = _keystream(clave_cifrado, sal, len(cifrado))
    return bytes(a ^ b for a, b in zip(cifrado, keystream))

def leer_texto(ruta, llave) -> str:
    datos = Path(ruta).read_bytes()
    if esta_cifrado(datos):
        datos = descifrar(datos, llave)
    return datos.decode("utf-8")
