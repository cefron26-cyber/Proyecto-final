import hashlib
import hmac
import os

import pytest

import credenciales as CR
import cripto

LLAVE = "una-llave-de-prueba-bastante-larga"
BUENAS = {"url_script": "https://script.google.com/macros/s/ABC/exec",
          "token": "token-123456", "llave": LLAVE}


def test_sin_archivo_hay_problemas(tmp_path):
    assert not any(CR.cargar(tmp_path).values())
    assert len(CR.problemas(CR.cargar(tmp_path))) == 3


def test_guardar_y_cargar(tmp_path):
    CR.guardar(tmp_path, BUENAS)
    assert CR.cargar(tmp_path) == BUENAS
    assert CR.problemas(CR.cargar(tmp_path)) == []


@pytest.mark.parametrize("campo,valor", [("url_script", "http://x.com/exec"),
                                         ("token", "corto"), ("llave", "corta")])
def test_rechaza_datos_invalidos(tmp_path, campo, valor):
    with pytest.raises(ValueError):
        CR.guardar(tmp_path, {**BUENAS, campo: valor})


def test_cifrar_y_descifrar():
    msg = "notas ñ á 10.0".encode()
    blob = cripto.cifrar(msg, LLAVE)
    assert cripto.esta_cifrado(blob)
    assert cripto.descifrar(blob, LLAVE) == msg


def test_llave_incorrecta_o_vacia():
    blob = cripto.cifrar(b"x", LLAVE)
    with pytest.raises(ValueError):
        cripto.descifrar(blob, "otra-llave-distinta-123")
    with pytest.raises(ValueError):
        cripto.cifrar(b"x", "")


def test_formato_compatible_con_la_app_del_coordinador():
    """Un archivo cifrado como lo hacía la versión anterior (llave dentro del
    código) se abre con la nueva usando la misma llave."""
    vieja = b"Liceo-Sahagun::cambia-esta-llave-y-ponla-igual-en-ambas-apps"
    sal = os.urandom(16)

    def derivar(etiqueta):
        return hmac.new(vieja, etiqueta + sal, hashlib.sha256).digest()

    msg = b'{"examen": "x"}'
    ks = cripto._keystream(derivar(b"cifrado"), sal, len(msg))
    cuerpo = cripto.MAGIA + sal + bytes(a ^ b for a, b in zip(msg, ks))
    blob = cuerpo + hmac.new(derivar(b"mac"), cuerpo, hashlib.sha256).digest()
    assert cripto.descifrar(blob, vieja) == msg
