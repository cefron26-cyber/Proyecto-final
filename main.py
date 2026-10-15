#!/usr/bin/env python3
"""
main.py — Calificador OMR (Kivy).

PASO 1: Configuración inicial (una vez) + menú con desplegables.
PASO 2: Estudiantes — lista del curso con código automático.
PASO 3: Exámenes — crear la clave de respuestas y (opcional) el PDF de la hoja.

Reutiliza gestor_salones.py y generador_pdf.py. La clave se guarda en el mismo
formato que lee lector_omr.py / registro_notas.py.
"""

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.graphics import (Color, RoundedRectangle, Line, Canvas, Scale, Ellipse, Rectangle,
                            PushMatrix, PopMatrix)
from kivy.factory import Factory
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.utils import platform
from kivy.uix.modalview import ModalView
from kivy.graphics.texture import Texture
from kivy.properties import NumericProperty, ListProperty, BooleanProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.animation import Animation

import os
import json
import shutil
import tempfile
import threading
from pathlib import Path
import gestor_salones as GS
import plataforma as PF
import layout_hoja as LH

BASE = GS.BASE_DIR  # carpeta "profesores"

ARCHIVO_LISTA = "lista_estudiantes.xlsx"


# ─────────────────────────────────────────────────────────────────────────────
# TEMA VISUAL · azul marino institucional + dorado, tarjetas blancas
# (solo apariencia, no lógica)
# ─────────────────────────────────────────────────────────────────────────────
AZUL     = (0.075, 0.161, 0.294, 1)   # #13294B  (azul del escudo)
AZUL_OSC = (0.047, 0.114, 0.220, 1)   # #0C1D38
DORADO   = (0.890, 0.663, 0.071, 1)   # #E3A912  (acento dorado)
FONDO    = (0.957, 0.965, 0.980, 1)   # #F4F6FA  (fondo de la app)
BLANCO   = (1, 1, 1, 1)
TEXTO    = (0.078, 0.125, 0.200, 1)   # #142033
GRIS     = (0.420, 0.451, 0.522, 1)   # #6B7385  (texto secundario)
BORDE    = (0.882, 0.898, 0.925, 1)   # #E1E5EC
TINTE    = (0.918, 0.941, 0.980, 1)   # #EAF0FA  (azul muy suave)
# Colores "con significado" para texto con markup (formato hexadecimal):
VERDE = "2E7D32"   # aprobó
ROJO  = "C62828"   # reprobó / error
AMBAR = "E09B00"   # por revisar
GRIS_HEX = "6B7385"

_DIR = Path(__file__).resolve().parent
_ESCUDO = _DIR / "assets" / "escudo_app.png"


def _registrar_fuentes():
    """Si hay fuentes en assets/fonts, reemplaza la fuente por defecto.
    Detecta el archivo sin importar el nombre exacto (Inter-Regular.ttf,
    Inter_18pt-Regular.ttf, etc.). Si no hay, la app sigue con la letra estándar.
    También registra "Titulos" (la versión gruesa) para los títulos de ventanas."""
    from kivy.resources import resource_find
    base = _DIR / "assets" / "fonts"
    ttfs = list(base.glob("*.ttf")) if base.exists() else []

    def _buscar(*claves):
        for t in ttfs:
            n = t.name.lower()
            if all(k in n for k in claves):
                return t
        return None

    bold = None
    if ttfs:
        regular = _buscar("regular") or ttfs[0]
        bold = _buscar("semibold") or _buscar("bold") or regular
        try:
            LabelBase.register(name="Roboto",
                               fn_regular=str(regular),
                               fn_bold=str(bold))
        except Exception:
            bold = None
    try:
        LabelBase.register(name="Titulos", fn_regular=str(
            bold or resource_find("data/fonts/Roboto-Bold.ttf")))
    except Exception:
        pass


_textura_escudo = None


def _textura_del_escudo():
    """Textura del escudo con mipmaps: se ve nítido y suave aunque se dibuje
    mucho más pequeño que la imagen original."""
    global _textura_escudo
    if _textura_escudo is None and _ESCUDO.exists():
        try:
            from kivy.core.image import Image as CoreImage
            _textura_escudo = CoreImage(str(_ESCUDO), mipmap=True).texture
        except Exception:
            _textura_escudo = None
    return _textura_escudo


def _fondo_tarjeta(w, color=BLANCO, radio=None, sombra=True):
    """Dibuja detrás del widget una tarjeta redondeada con sombra suave."""
    radio = dp(16) if radio is None else radio
    capas = []
    with w.canvas.before:
        if sombra:
            for extra, baja, alfa in ((dp(3), dp(4), 0.025), (dp(1.5), dp(2.5), 0.04),
                                      (dp(0.5), dp(1), 0.06)):
                Color(rgba=(0.05, 0.09, 0.17, alfa))
                capas.append((RoundedRectangle(radius=[radio + extra]), extra, baja))
        w._color_fondo = Color(rgba=color)
        capas.append((RoundedRectangle(radius=[radio]), 0, 0))

    def _sync(*_):
        for rect, extra, baja in capas:
            rect.pos = (w.x - extra, w.y - extra - baja)
            rect.size = (w.width + 2 * extra, w.height + 2 * extra)
    w.bind(pos=_sync, size=_sync)
    _sync()


class Tarjeta(BoxLayout):
    """Caja blanca redondeada con sombra, para agrupar contenido."""

    def __init__(self, color=BLANCO, radio=None, sombra=True, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        _fondo_tarjeta(self, color, radio, sombra)


class InsigniaEscudo(Widget):
    """El escudo del colegio sobre un círculo blanco con aro dorado."""

    def __init__(self, tam, **kw):
        super().__init__(size_hint=(None, None), size=(tam, tam), **kw)
        tex = _textura_del_escudo()
        with self.canvas:
            Color(rgba=(0, 0, 0, 0.12))
            self._sombra = Ellipse()
            Color(rgba=BLANCO)
            self._circulo = Ellipse()
            Color(rgba=DORADO)
            self._aro = Line(width=dp(1.3))
            Color(1, 1, 1, 1)
            self._img = Rectangle(texture=tex) if tex is not None else None
        if tex is None:
            self._iniciales = Label(text="LS", bold=True, color=AZUL, font_size=tam * 0.32)
            self.add_widget(self._iniciales)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        x, y = self.pos
        t = self.width
        self._sombra.pos = (x, y - dp(1.5))
        self._sombra.size = (t, t)
        self._circulo.pos = (x, y)
        self._circulo.size = (t, t)
        self._aro.circle = (x + t / 2, y + t / 2, t / 2 - dp(2.5))
        s = t * 0.70
        if self._img is not None:
            self._img.pos = (x + (t - s) / 2, y + (t - s) / 2)
            self._img.size = (s, s)
        else:
            self._iniciales.pos = self.pos
            self._iniciales.size = self.size


def _vibrar(duracion: float = 0.02):
    """Vibración corta SOLO en Android. En PC no hace nada (no rompe la prueba)."""
    try:
        if platform == "android":
            from plyer import vibrator  # type: ignore  # solo existe en Android
            vibrator.vibrate(duracion)
    except Exception:
        pass


def _solicitar_permisos_android():
    """Solo Android 9 o anterior necesita permiso para guardar en Descargas.
    Desde Android 10 no se pide ningún permiso: las fotos y planillas se eligen
    con el selector del sistema y Descargas se usa a través de MediaStore."""
    try:
        if platform != "android":
            return
        from jnius import autoclass  # type: ignore
        if autoclass("android.os.Build$VERSION").SDK_INT <= 28:
            from android.permissions import request_permissions, Permission  # type: ignore
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE])
    except Exception:
        pass


def _ajustar_texto(lb):
    """Hace que la etiqueta respete su ancho/alto (para alinear a la izquierda)."""
    lb.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, i.height)))
    return lb


def _redibujar_al_cambiar(w, funcion):
    """Llama a funcion() cuando el widget se mueve o cambia de tamaño, pero en el
    siguiente cuadro: así right/top/center ya tienen su valor final."""
    disparador = Clock.create_trigger(lambda dt: funcion(), -1)
    w.bind(pos=lambda *_: disparador(), size=lambda *_: disparador())


class Encabezado(BoxLayout):
    """Barra azul marino con el escudo, el título y el subtítulo de cada pantalla."""

    def __init__(self, titulo, subtitulo="Liceo Sahagún", **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(78), padding=[dp(12), dp(12), dp(12), dp(12)],
                         spacing=dp(12), **kw)
        _fondo_tarjeta(self, AZUL, dp(20))

        caja_escudo = AnchorLayout(size_hint=(None, 1), width=dp(54))
        caja_escudo.add_widget(InsigniaEscudo(dp(52)))
        self.add_widget(caja_escudo)

        caja = BoxLayout(orientation="vertical", spacing=dp(1))
        lbl_t = Label(text=titulo, bold=True, color=BLANCO, font_size="19sp",
                      halign="left", valign="bottom", shorten=True,
                      shorten_from="right")
        sub = Label(text=subtitulo, color=(0.95, 0.80, 0.42, 1), font_size="12.5sp",
                    halign="left", valign="top", shorten=True, shorten_from="right")
        caja.add_widget(_ajustar_texto(lbl_t))
        caja.add_widget(_ajustar_texto(sub))
        self.add_widget(caja)

        # Botón de cerrar la app (esquina superior derecha), con confirmación
        cerrar = AnchorLayout(size_hint=(None, 1), width=dp(36), anchor_y="top")
        btn_x = BotonCerrar(size_hint=(None, None), size=(dp(34), dp(34)))
        btn_x.bind(on_release=lambda *_: pedir_salir())
        cerrar.add_widget(btn_x)
        self.add_widget(cerrar)


class Portada(FloatLayout):
    """Encabezado grande de la pantalla de inicio: escudo, colegio y saludo."""

    def __init__(self, saludo, detalle, **kw):
        super().__init__(size_hint_y=None, height=dp(206), **kw)
        _fondo_tarjeta(self, AZUL, dp(24))
        caja = BoxLayout(orientation="vertical", spacing=dp(4),
                         padding=[dp(16), dp(18), dp(16), dp(16)],
                         pos_hint={"x": 0, "y": 0}, size_hint=(1, 1))
        fila_escudo = AnchorLayout(size_hint_y=None, height=dp(84))
        fila_escudo.add_widget(InsigniaEscudo(dp(82)))
        caja.add_widget(fila_escudo)
        caja.add_widget(Widget(size_hint_y=None, height=dp(6)))
        colegio = Label(text="LICEO SAHAGÚN", bold=True, font_size="11.5sp",
                        color=(0.95, 0.80, 0.42, 1), size_hint_y=None, height=dp(16))
        titulo = Label(text=saludo, bold=True, font_size="22sp", color=BLANCO,
                       size_hint_y=None, height=dp(30), shorten=True)
        sub = Label(text=detalle, font_size="13sp", color=(0.78, 0.83, 0.92, 1),
                    size_hint_y=None, height=dp(20), shorten=True)
        for lb in (colegio, titulo, sub):
            lb.halign = "center"
            lb.valign = "middle"
            caja.add_widget(_ajustar_texto(lb))
        self.add_widget(caja)
        btn_x = BotonCerrar(size_hint=(None, None), size=(dp(34), dp(34)),
                            pos_hint={"right": 0.975, "top": 0.95})
        btn_x.bind(on_release=lambda *_: pedir_salir())
        self.add_widget(btn_x)


class BotonMenu(Button):
    """Tarjeta del menú del curso: ícono, título, una línea de ayuda y una flecha."""

    def __init__(self, icono="", titulo="", detalle="", **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(76))
        super().__init__(markup=True, **kw)
        self._icono = icono
        self.text = (f"[b]{titulo}[/b]\n[size=12.5sp][color={GRIS_HEX}]{detalle}"
                     f"[/color][/size]")
        self.halign = "left"
        self.valign = "middle"
        self.color = TEXTO
        self.bold = False
        self.line_height = 1.15
        self.color_fondo = (0, 0, 0, 0)
        self.color_fondo_down = (0, 0, 0, 0)
        _fondo_tarjeta(self, BLANCO, dp(18))
        self.bind(state=lambda *_: setattr(
            self._color_fondo, "rgba", BLANCO if self.state == "normal" else TINTE))
        # El ícono va en su propio grupo: así se redibuja sin borrar el resto
        # de canvas.after (ahí está el cierre de la animación al tocar)
        self._g_icono = Canvas()
        self.canvas.after.add(self._g_icono)
        _redibujar_al_cambiar(self, self._redibujar)

    def _redibujar(self, *_):
        self.padding = [dp(74), 0, dp(40), 0]
        self.text_size = (self.width, self.height)
        self._g_icono.clear()
        d = dp(44)
        cx, cy = self.x + dp(16) + d / 2, self.center_y
        s = dp(22)
        with self._g_icono:
            Color(rgba=TINTE)
            RoundedRectangle(pos=(cx - d / 2, cy - d / 2), size=(d, d), radius=[dp(13)])
            Color(rgba=AZUL)
            self._dibujar_icono(self._icono, cx - s / 2, cy - s / 2, s)
            # Flecha ">" a la derecha
            Color(rgba=(0.70, 0.73, 0.79, 1))
            fx, fy, f = self.right - dp(22), self.center_y, dp(5)
            Line(points=[fx - f, fy + f * 1.4, fx, fy, fx - f, fy - f * 1.4],
                 width=dp(1.3), cap="round", joint="round")

    @staticmethod
    def _dibujar_icono(nombre, x, y, s):
        w = dp(1.3)
        if nombre == "estudiantes":
            Line(circle=(x + s * 0.36, y + s * 0.70, s * 0.17), width=w)
            Line(ellipse=(x + s * 0.06, y - s * 0.10, s * 0.60, s * 0.62, -90, 90), width=w)
            Line(circle=(x + s * 0.74, y + s * 0.64, s * 0.13), width=w)
            Line(ellipse=(x + s * 0.54, y - s * 0.02, s * 0.42, s * 0.46, 0, 90), width=w)
        elif nombre == "examenes":
            Line(rounded_rectangle=(x + s * 0.14, y, s * 0.72, s, s * 0.12), width=w)
            Line(points=[x + s * 0.32, y + s * 0.70, x + s * 0.68, y + s * 0.70], width=w,
                 cap="round")
            Line(points=[x + s * 0.32, y + s * 0.50, x + s * 0.68, y + s * 0.50], width=w,
                 cap="round")
            Line(points=[x + s * 0.32, y + s * 0.30, x + s * 0.54, y + s * 0.30], width=w,
                 cap="round")
        elif nombre == "calificar":
            Line(rounded_rectangle=(x, y + s * 0.08, s, s * 0.74, s * 0.14), width=w)
            Line(points=[x + s * 0.32, y + s * 0.82, x + s * 0.40, y + s * 0.96,
                         x + s * 0.60, y + s * 0.96, x + s * 0.68, y + s * 0.82], width=w,
                 joint="round")
            Line(circle=(x + s * 0.50, y + s * 0.45, s * 0.20), width=w)
        elif nombre == "registro":
            Line(points=[x + s * 0.12, y + s * 0.04, x + s * 0.12, y + s * 0.96], width=w,
                 cap="round")
            Line(points=[x + s * 0.04, y + s * 0.08, x + s * 0.96, y + s * 0.08], width=w,
                 cap="round")
            for i, alto in enumerate((0.40, 0.68, 0.52)):
                bx = x + s * (0.28 + i * 0.24)
                Line(rounded_rectangle=(bx, y + s * 0.16, s * 0.14, s * alto, s * 0.04),
                     width=w)


class Pildora(Label):
    """Etiqueta con fondo azul muy suave redondeado (para el curso elegido)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.color = AZUL
        self.font_size = "13.5sp"
        self.halign = "center"
        self.valign = "middle"
        self.markup = True
        with self.canvas.before:
            Color(rgba=TINTE)
            self._r = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *_):
        self._r.pos = self.pos
        self._r.size = self.size
        self.text_size = (self.width - dp(24), self.height)


class BotonCerrar(Button):
    """Botón redondo con una X, para cerrar la app (va en el encabezado)."""

    def __init__(self, **kw):
        super().__init__(text="", **kw)
        self._icono = Canvas()
        self.canvas.after.add(self._icono)
        _redibujar_al_cambiar(self, self._redibujar)

    def _redibujar(self, *_):
        g = self._icono
        g.clear()
        m = self.width * 0.35
        g.add(Color(rgba=(1, 1, 1, 0.85)))
        g.add(Line(points=[self.x + m, self.y + m, self.right - m, self.top - m],
                   width=dp(1.3), cap="round"))
        g.add(Line(points=[self.x + m, self.top - m, self.right - m, self.y + m],
                   width=dp(1.3), cap="round"))


class BotonIcono(Button):
    """Botón cuadrado pequeño con un ícono dibujado: 'borrar' o 'descargar'."""

    def __init__(self, icono, peligro=False, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("size", (dp(44), dp(44)))
        super().__init__(text="", **kw)
        self._icono_nombre = icono
        self._tinta = (0.776, 0.157, 0.157, 1) if peligro else AZUL
        if peligro:
            self.color_fondo = (0.992, 0.925, 0.925, 1)
            self.color_fondo_down = (0.980, 0.851, 0.851, 1)
        else:
            self.color_fondo = TINTE
            self.color_fondo_down = (0.851, 0.890, 0.957, 1)
        self._g = Canvas()
        self.canvas.after.add(self._g)
        _redibujar_al_cambiar(self, self._redibujar)

    def _redibujar(self, *_):
        self._g.clear()
        s = dp(18)
        x, y = self.center_x - s / 2, self.center_y - s / 2
        w = dp(1.4)
        with self._g:
            Color(rgba=self._tinta)
            if self._icono_nombre == "borrar":
                Line(points=[x + s * 0.06, y + s * 0.80, x + s * 0.94, y + s * 0.80],
                     width=w, cap="round")
                Line(points=[x + s * 0.36, y + s * 0.80, x + s * 0.40, y + s * 0.96,
                             x + s * 0.60, y + s * 0.96, x + s * 0.64, y + s * 0.80],
                     width=w, joint="round")
                Line(points=[x + s * 0.18, y + s * 0.80, x + s * 0.26, y,
                             x + s * 0.74, y, x + s * 0.82, y + s * 0.80],
                     width=w, joint="round")
                Line(points=[x + s * 0.42, y + s * 0.20, x + s * 0.42, y + s * 0.62],
                     width=w, cap="round")
                Line(points=[x + s * 0.58, y + s * 0.20, x + s * 0.58, y + s * 0.62],
                     width=w, cap="round")
            elif self._icono_nombre == "descargar":
                Line(points=[x + s * 0.5, y + s * 0.98, x + s * 0.5, y + s * 0.30],
                     width=w, cap="round")
                Line(points=[x + s * 0.24, y + s * 0.56, x + s * 0.5, y + s * 0.30,
                             x + s * 0.76, y + s * 0.56], width=w, cap="round",
                     joint="round")
                Line(points=[x + s * 0.06, y + s * 0.30, x + s * 0.06, y,
                             x + s * 0.94, y, x + s * 0.94, y + s * 0.30],
                     width=w, cap="round", joint="round")


class Casilla(ButtonBehavior, BoxLayout):
    """Fila tocable con una casilla de verificación propia y un texto."""
    active = BooleanProperty(False)

    def __init__(self, texto="", active=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(44))
        super().__init__(spacing=dp(12), **kw)
        self.active = active
        self._caja = Widget(size_hint=(None, 1), width=dp(24))
        self.add_widget(self._caja)
        self.lbl = _ajustar_texto(Label(text=texto, halign="left", valign="middle",
                                        font_size="14.5sp", markup=True))
        self.add_widget(self.lbl)
        self._g = Canvas()
        self._caja.canvas.add(self._g)
        _redibujar_al_cambiar(self._caja, self._dibujar)
        self.bind(active=self._dibujar)

    def on_release(self):
        self.active = not self.active

    def _dibujar(self, *_):
        c = self._caja
        t = dp(22)
        x, y = c.x, c.center_y - t / 2
        self._g.clear()
        with self._g:
            if self.active:
                Color(rgba=AZUL)
                RoundedRectangle(pos=(x, y), size=(t, t), radius=[dp(6)])
                Color(rgba=BLANCO)
                Line(points=[x + t * 0.26, y + t * 0.52, x + t * 0.44, y + t * 0.32,
                             x + t * 0.76, y + t * 0.70], width=dp(1.6), cap="round",
                     joint="round")
            else:
                Color(rgba=BLANCO)
                RoundedRectangle(pos=(x, y), size=(t, t), radius=[dp(6)])
                Color(rgba=(0.74, 0.77, 0.83, 1))
                Line(rounded_rectangle=(x, y, t, t, dp(6)), width=dp(1.2))


def _boton_volver(texto, destino):
    """Botón discreto (sin relleno) para volver a otra pantalla."""
    btn = Factory.BotonTexto(text=f"←  {texto}", size_hint_y=None, height=dp(44))
    btn.bind(on_release=lambda *_: setattr(App.get_running_app().sm, "current", destino))
    return btn


def _vacio(titulo, detalle="", alto=110):
    """Mensaje amable para cuando una lista todavía no tiene nada."""
    lbl = Label(text=f"[b]{titulo}[/b]" + (f"\n[size=13sp][color={GRIS_HEX}]{detalle}"
                                          f"[/color][/size]" if detalle else ""),
                markup=True, halign="center", valign="middle", size_hint_y=None,
                height=dp(alto), color=TEXTO, font_size="15.5sp", line_height=1.25)
    lbl.bind(width=lambda i, w: setattr(i, "text_size", (w - dp(24), None)))
    return lbl


def pedir_salir():
    """Pide confirmación antes de cerrar la app."""
    confirmar("¿Ya te vas?", "Todo tu trabajo queda guardado.",
              "Salir", lambda: App.get_running_app().stop(), peligro=False)


# ── Respuesta al tocar: TODOS los botones se hunden un poco y vibran ─────────
class _Pulso(Widget):   # Animation solo anima widgets
    valor = NumericProperty(1.0)   # ("s" no sirve: Animation lo usa como "paso")


def _preparar_pulso(w):
    """Agrega al botón una escala (alrededor de su centro) que se puede animar.
    Se agrega la primera vez que se toca: PushMatrix/Scale al inicio de
    canvas.before y PopMatrix al final de canvas.after."""
    p = getattr(w, "_pulso", None)
    if p is None:
        p = _Pulso()
        escala = Scale(1, 1, 1)
        w.canvas.before.insert(0, escala)
        w.canvas.before.insert(0, PushMatrix())
        w.canvas.after.add(PopMatrix())

        def _aplicar(_p, v):
            escala.origin = w.center
            escala.x = escala.y = v
            w.canvas.ask_update()
        p.bind(valor=_aplicar)
        w._pulso = p
    return p


_press_original = ButtonBehavior._do_press
_release_original = ButtonBehavior._do_release


def _do_press_con_pulso(self):
    _press_original(self)
    _vibrar()
    try:
        p = _preparar_pulso(self)
        Animation.cancel_all(p)
        Animation(valor=0.96, d=0.07, t="out_quad").start(p)
    except Exception:
        pass


def _do_release_con_pulso(self, *args):
    _release_original(self, *args)
    p = getattr(self, "_pulso", None)
    if p is not None:
        Animation.cancel_all(p)
        Animation(valor=1.0, d=0.22, t="out_back").start(p)


# Mismo nombre que los originales: Kivy a veces programa el "soltar" para un
# instante después buscándolo por su NOMBRE; con otro nombre, la app se cerraba.
_do_press_con_pulso.__name__ = "_do_press"
_do_release_con_pulso.__name__ = "_do_release"
ButtonBehavior._do_press = _do_press_con_pulso
ButtonBehavior._do_release = _do_release_con_pulso


class CirculoProgreso(Widget):
    """
    Anillo de progreso animado.
      • Arco dorado (grueso): cuánto se ha avanzado; crece suavemente.
      • Arco azul (fino, por dentro): gira mientras se trabaja, para que se
        note actividad aunque una foto tarde en procesarse.
      • En el centro, el porcentaje.
    """
    valor = NumericProperty(0.0)          # 0..1 (se anima con animar_a)
    giro = NumericProperty(0.0)           # ángulo del arco azul
    color_avance = ListProperty(list(DORADO))

    def __init__(self, con_porcentaje=True, **kw):
        self._con_porcentaje = con_porcentaje
        super().__init__(**kw)
        with self.canvas:
            Color(rgba=(0.906, 0.922, 0.949, 1))
            self._pista = Line(width=dp(6))
            self._c_avance = Color(rgba=self.color_avance)
            self._avance = Line(width=dp(6), cap="round")
            Color(rgba=AZUL)
            self._giro = Line(width=dp(2.2), cap="round")
        self.lbl = Label(markup=True, halign="center", valign="middle", color=AZUL)
        self.add_widget(self.lbl)
        self.bind(pos=self._dibujar, size=self._dibujar, valor=self._dibujar,
                  giro=self._dibujar, color_avance=self._dibujar)
        self._reloj = Clock.schedule_interval(self._girar, 1 / 60.0)

    def _girar(self, dt):
        self.giro = (self.giro + 260 * dt) % 360

    def _dibujar(self, *_):
        cx, cy = self.center
        r = min(self.width, self.height) / 2 - dp(8)
        self._pista.circle = (cx, cy, r)
        self._c_avance.rgba = self.color_avance
        if self.valor > 0.001:
            self._avance.circle = (cx, cy, r, 0, 360 * min(self.valor, 1.0))
        else:
            self._avance.points = []
        if self._reloj is not None:
            self._giro.circle = (cx, cy, r - dp(12), self.giro, self.giro + 80)
        else:
            self._giro.points = []
        self.lbl.size = self.size
        self.lbl.pos = self.pos
        self.lbl.text_size = self.size
        pct = int(round(self.valor * 100))
        self.lbl.text = (f"[size=34sp][b]{pct}[/b][/size][size=16sp][b] %[/b][/size]"
                         if self._con_porcentaje else "")

    def animar_a(self, valor):
        Animation.cancel_all(self, "valor")
        Animation(valor=valor, d=0.45, t="out_cubic").start(self)

    def detener(self):
        """Deja de girar el arco azul (el trabajo terminó)."""
        if self._reloj is not None:
            self._reloj.cancel()
            self._reloj = None
        self._dibujar()


class _VentanaSinRastro(ModalView):
    """ModalView que fuerza el repintado al cerrarse: si no, en algunos
    equipos la tarjeta quedaba "pegada" en pantalla hasta el siguiente toque."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(_is_open=self._al_cerrarse)

    @staticmethod
    def _al_cerrarse(_inst, abierto):
        if not abierto:
            Clock.schedule_once(lambda dt: Window.canvas.ask_update(), 0)


def _tarjeta_blanca(**kw):
    tarjeta = BoxLayout(orientation="vertical", **kw)
    with tarjeta.canvas.before:
        Color(rgba=BLANCO)
        fondo = RoundedRectangle(radius=[dp(18)])
    tarjeta.bind(pos=lambda w, *_: setattr(fondo, "pos", w.pos),
                 size=lambda w, *_: setattr(fondo, "size", w.size))
    return tarjeta


class PopupEspera(_VentanaSinRastro):
    """Ventana "Un momento…" con el anillo girando (sin porcentaje)."""

    def __init__(self, mensaje, **kw):
        super().__init__(size_hint=(0.8, None), height=dp(250), auto_dismiss=False,
                         background_color=(0, 0, 0, 0),
                         overlay_color=(0.05, 0.08, 0.15, 0.6), **kw)
        tarjeta = _tarjeta_blanca(padding=[dp(20), dp(18)], spacing=dp(10))
        caja = AnchorLayout(size_hint_y=None, height=dp(130))
        circulo = CirculoProgreso(size_hint=(None, None), size=(dp(120), dp(120)),
                                  con_porcentaje=False)
        caja.add_widget(circulo)
        lbl = Label(text=mensaje, bold=True, color=AZUL, font_size="16sp",
                    halign="center", valign="middle")
        lbl.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, None)))
        tarjeta.add_widget(caja)
        tarjeta.add_widget(lbl)
        self.add_widget(tarjeta)


class PopupProgreso(_VentanaSinRastro):
    """Ventana de "Calificando…" con anillo de progreso, contadores y Cancelar."""

    def __init__(self, titulo, subtitulo, total, al_cancelar, **kw):
        super().__init__(size_hint=(0.9, None), height=dp(440), auto_dismiss=False,
                         background_color=(0, 0, 0, 0),
                         overlay_color=(0.05, 0.08, 0.15, 0.6), **kw)
        self.total = total
        self._al_cancelar = al_cancelar
        self._cuenta = {"ok": 0, "revisar": 0, "error": 0}

        tarjeta = _tarjeta_blanca(padding=[dp(22), dp(20)], spacing=dp(6))

        def etiqueta(texto, alto, **kw):
            lb = Label(text=texto, size_hint_y=None, height=dp(alto), halign="center",
                       valign="middle", shorten=True, shorten_from="center", **kw)
            lb.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, i.height)))
            return lb

        self.lbl_titulo = etiqueta(titulo, 28, bold=True, color=AZUL, font_size="19sp")
        self.lbl_sub = etiqueta(subtitulo, 20, color=GRIS, font_size="13sp")
        caja = AnchorLayout(size_hint_y=None, height=dp(190))
        self.circulo = CirculoProgreso(size_hint=(None, None), size=(dp(176), dp(176)))
        caja.add_widget(self.circulo)
        self.lbl_estado = etiqueta("Preparando…", 24, bold=True, font_size="16sp")
        self.lbl_archivo = etiqueta("", 18, color=GRIS, font_size="12sp")
        self.lbl_cuenta = etiqueta("", 22, markup=True, font_size="13sp")
        self.zona_boton = BoxLayout(size_hint_y=None, height=dp(48))
        self.btn = Factory.BotonOutline(text="Detener")
        self.btn.bind(on_release=self._cancelar)
        self.zona_boton.add_widget(self.btn)

        for w in (self.lbl_titulo, self.lbl_sub, caja, self.lbl_estado,
                  self.lbl_archivo, self.lbl_cuenta, Widget(size_hint_y=None, height=dp(4)),
                  self.zona_boton):
            tarjeta.add_widget(w)
        self.add_widget(tarjeta)
        self._mostrar_cuenta()

    def _mostrar_cuenta(self):
        c = self._cuenta
        self.lbl_cuenta.text = (f"[color={VERDE}]{c['ok']} bien[/color]   ·   "
                                f"[color={AMBAR}]{c['revisar']} por revisar[/color]   ·   "
                                f"[color={ROJO}]{c['error']} sin leer[/color]")

    def _cancelar(self, *_):
        self.btn.disabled = True
        self.btn.text = "Deteniendo…"
        self.lbl_estado.text = "Terminando la hoja en curso…"
        self._al_cancelar()

    def empezar(self, i, nombre):
        """Se empieza a procesar la hoja i (0-based)."""
        if not self.btn.disabled:
            self.lbl_estado.text = f"Calificando hoja {i + 1} de {self.total}"
        self.lbl_archivo.text = nombre

    def avance(self, hechas, estado):
        """Terminó una hoja. estado: 'ok', 'revisar' o 'error'."""
        self._cuenta[estado] += 1
        self._mostrar_cuenta()
        self.circulo.animar_a(hechas / float(self.total))

    def terminar(self, cuenta, cancelado, al_cerrar):
        """Muestra el resumen final y cambia el botón a 'Ver resultados'."""
        self._cuenta = cuenta
        self._mostrar_cuenta()
        self.circulo.detener()
        hechas = sum(cuenta.values())
        if cancelado:
            self.lbl_titulo.text = "Calificación detenida"
            self.lbl_estado.text = f"Alcanzamos a calificar {hechas} de {self.total}"
        else:
            self.lbl_titulo.text = "¡Listo!"
            self.circulo.animar_a(1.0)
            self.lbl_estado.text = (f"{hechas} hoja calificada" if hechas == 1
                                    else f"{hechas} hojas calificadas")
        self.lbl_archivo.text = ("Dale un vistazo a las marcadas en ámbar o rojo."
                                 if cuenta["revisar"] or cuenta["error"] else "")
        # Anillo verde si todo salió bien; ámbar si hay algo que revisar
        self.circulo.color_avance = list(
            (0.180, 0.490, 0.196, 1) if not (cuenta["revisar"] or cuenta["error"])
            else (0.976, 0.659, 0.145, 1))
        self.zona_boton.clear_widgets()
        btn = Factory.BotonAccion(text="Ver resultados")
        btn.bind(on_release=lambda *_: (self.dismiss(), al_cerrar()))
        self.zona_boton.add_widget(btn)


def _caption(texto):
    """Etiqueta pequeña gris que va encima de un campo."""
    lb = Label(text=texto, color=GRIS, font_size="12.5sp",
               size_hint_y=None, height=dp(20), halign="left", valign="middle")
    lb.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, i.height)))
    return lb


# Tema visual (embebido para no depender de un archivo .kv externo) -------------
_TEMA_KV = """
#:set C_AZUL       (0.075, 0.161, 0.294, 1)
#:set C_AZUL_OSC   (0.047, 0.114, 0.220, 1)
#:set C_DORADO     (0.890, 0.663, 0.071, 1)
#:set C_DORADO_OSC (0.800, 0.588, 0.047, 1)
#:set C_ROJO       (0.776, 0.157, 0.157, 1)
#:set C_ROJO_OSC   (0.620, 0.118, 0.118, 1)
#:set C_TEXTO      (0.078, 0.125, 0.200, 1)
#:set C_GRIS       (0.420, 0.451, 0.522, 1)
#:set C_BORDE      (0.882, 0.898, 0.925, 1)
#:set C_TINTE      (0.918, 0.941, 0.980, 1)
#:set C_TINTE_OSC  (0.851, 0.890, 0.957, 1)
#:set C_BLANCO     (1, 1, 1, 1)
#:set C_DESACT     (0.80, 0.82, 0.86, 1)

<Label>:
    color: C_TEXTO
    font_size: '15sp'

# Todos los botones dibujan su fondo con estas propiedades; cada estilo solo
# cambia los colores (así ningún estilo tapa a otro).
<Button>:
    background_normal: ''
    background_down: ''
    background_disabled_normal: ''
    background_disabled_down: ''
    background_color: 0, 0, 0, 0
    color: C_BLANCO
    disabled_color: (1, 1, 1, 0.75)
    bold: True
    font_size: '15sp'
    color_fondo: C_AZUL
    color_fondo_down: C_AZUL_OSC
    color_borde: (0, 0, 0, 0)
    radio: dp(14)
    canvas.before:
        Color:
            rgba: C_DESACT if self.disabled else ((self.color_fondo or C_AZUL) if self.state == 'normal' else (self.color_fondo_down or C_AZUL_OSC))
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radio or 0,]
        Color:
            rgba: self.color_borde or (0, 0, 0, 0)
        Line:
            rounded_rectangle: (self.x + 0.5, self.y + 0.5, self.width - 1, self.height - 1, self.radio or 0)
            width: dp(0.9)

# Principal: dorado con texto azul marino
<BotonAccion@Button>:
    color: C_AZUL
    color_fondo: C_DORADO
    color_fondo_down: C_DORADO_OSC

<BotonPeligro@Button>:
    color: C_BLANCO
    color_fondo: C_ROJO
    color_fondo_down: C_ROJO_OSC

# Secundario: blanco con borde fino
<BotonOutline@Button>:
    color: C_AZUL
    color_fondo: C_BLANCO
    color_fondo_down: C_TINTE
    color_borde: C_BORDE

# Terciario: azul muy suave
<BotonSuave@Button>:
    color: C_AZUL
    color_fondo: C_TINTE
    color_fondo_down: C_TINTE_OSC

# Solo texto (volver, enlaces)
<BotonTexto@Button>:
    color: C_AZUL
    bold: False
    color_fondo: (0, 0, 0, 0)
    color_fondo_down: C_TINTE

<FilaLista@Button>:
    color: C_TEXTO
    bold: False
    markup: True
    halign: 'left'
    valign: 'middle'
    padding: [dp(16), 0]
    text_size: self.size
    font_size: '15sp'
    color_fondo: C_BLANCO
    color_fondo_down: C_TINTE
    color_borde: C_BORDE
    radio: dp(12)

<BotonCerrar>:
    color_fondo: (1, 1, 1, 0.12)
    color_fondo_down: (1, 1, 1, 0.28)
    radio: self.height / 2.

<Spinner>:
    color: C_TEXTO
    bold: False
    font_size: '15sp'
    halign: 'left'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    padding: [dp(14), 0, dp(38), 0]
    text_size: self.size
    color_fondo: C_BLANCO
    color_fondo_down: C_TINTE
    color_borde: C_BORDE
    radio: dp(12)
    canvas.after:
        Color:
            rgba: C_GRIS
        Line:
            points: [self.right - dp(24), self.center_y + dp(2.5), self.right - dp(19), self.center_y - dp(2.5), self.right - dp(14), self.center_y + dp(2.5)]
            width: dp(1.3)
            cap: 'round'
            joint: 'round'

<SpinnerOption>:
    color: C_TEXTO
    bold: False
    halign: 'left'
    valign: 'middle'
    padding: [dp(16), 0]
    text_size: self.size
    height: dp(46)
    color_fondo: C_BLANCO
    color_fondo_down: C_TINTE
    radio: 0
    canvas.after:
        Color:
            rgba: C_BORDE
        Rectangle:
            pos: self.x + dp(12), self.y
            size: self.width - dp(24), dp(1)

<TextInput>:
    background_normal: ''
    background_active: ''
    background_color: C_BLANCO
    foreground_color: C_TEXTO
    cursor_color: C_AZUL
    cursor_width: dp(1.6)
    hint_text_color: (0.62, 0.65, 0.71, 1)
    selection_color: (0.890, 0.663, 0.071, 0.35)
    font_size: '15sp'
    padding: [dp(14), (self.height - self.line_height) / 2. if not self.multiline else dp(12), dp(14), 0]
    canvas.after:
        Color:
            rgba: C_AZUL if self.focus else C_BORDE
        Line:
            rounded_rectangle: (self.x + 0.5, self.y + 0.5, self.width - 1, self.height - 1, dp(12))
            width: dp(1.4) if self.focus else dp(1)

<Popup>:
    background: ''
    background_color: 0, 0, 0, 0
    # El oscurecido de Kivy se dibuja en "canvas", encima del fondo blanco; por eso
    # se apaga y se dibuja aquí, antes de la tarjeta.
    overlay_color: (0, 0, 0, 0)
    title_color: C_TEXTO
    title_size: '18sp'
    title_font: 'Titulos'
    separator_color: C_BORDE
    separator_height: dp(1)
    canvas.before:
        Color:
            rgba: (0.04, 0.07, 0.14, 0.55 * self._anim_alpha)
        Rectangle:
            size: self._window.size if self._window else (0, 0)
        Color:
            rgba: C_BLANCO
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(22),]
"""

Builder.load_string(_TEMA_KV)


def _subdirs(p):
    return sorted(d.name for d in p.iterdir() if d.is_dir()) if p.exists() else []


def aviso(titulo, mensaje):
    _popup_texto(titulo, mensaje, [("Entendido", "normal", None)])


def confirmar(titulo, mensaje, texto_si, al_si, peligro=True):
    """Pregunta antes de algo que no se puede deshacer."""
    _popup_texto(titulo, mensaje, [("No, volver", "outline", None),
                                   (texto_si, "peligro" if peligro else "accion", al_si)])


def aviso_archivo(titulo, mensaje, ref, nombre):
    """Aviso de archivo guardado, con botones para abrirlo o compartirlo."""
    def _abrir():
        err = PF.abrir(ref, nombre)
        if err:
            aviso("No pudimos abrirlo", f"Búscalo en tu carpeta de Descargas.\n\n({err})")

    def _compartir():
        err = PF.compartir(ref, nombre)
        if err:
            aviso("No pudimos compartirlo", err)

    _popup_texto(titulo, mensaje, [("Abrir", "accion", _abrir),
                                   ("Compartir" if PF.ES_ANDROID else "Ver carpeta", "normal", _compartir),
                                   ("Listo", "outline", None)])


def _popup_texto(titulo, mensaje, botones, alto=0.55):
    """Ventana con un texto y una fila de botones [(texto, estilo, acción)].
    estilo: 'accion' (dorado), 'peligro' (rojo), 'outline' o 'normal' (azul)."""
    cont = BoxLayout(orientation="vertical", padding=[dp(8), dp(12), dp(8), dp(4)],
                     spacing=dp(14))
    lbl = Label(text=str(mensaje), halign="center", valign="top", size_hint_y=None,
                color=TEXTO, line_height=1.2)
    lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
    lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1]))
    scroll = ScrollView()
    scroll.add_widget(lbl)
    cont.add_widget(scroll)
    fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    popup = Popup(title=titulo, content=cont, size_hint=(0.92, alto))
    clases = {"accion": Factory.BotonAccion, "peligro": Factory.BotonPeligro,
              "outline": Factory.BotonOutline, "normal": Factory.BotonSuave}
    for texto, estilo, accion in botones:
        btn = clases[estilo](text=texto, font_size="14sp")

        def _pulsar(*_, a=accion):
            popup.dismiss()
            if a is not None:
                a()
        btn.bind(on_release=_pulsar)
        fila.add_widget(btn)
    cont.add_widget(fila)
    popup.open()
    return popup


def en_segundo_plano(mensaje, trabajo, al_terminar):
    """
    Corre trabajo() en otro hilo mostrando una ventana de espera (la interfaz
    no se congela). Al final llama a al_terminar(resultado, error) en el hilo
    de la interfaz; error es None si todo salió bien.
    """
    espera = PopupEspera(mensaje)
    espera.open()

    def _hilo():
        try:
            res, err = trabajo(), None
        except Exception as e:
            res, err = None, e

        def _fin(dt):
            espera.dismiss()
            al_terminar(res, err)
        Clock.schedule_once(_fin, 0)
    threading.Thread(target=_hilo, daemon=True).start()


def codigo_de(posicion: int) -> str:
    return f"{posicion:03d}"


def nota_local(aciertos, total):
    """Nota 0-10 truncada a 1 decimal, con piso 1.0 (igual que el lector)."""
    if not total:
        return 0.0
    nota = 10.0 * aciertos / total
    nota = int(nota * 10 + 1e-9) / 10.0
    return max(1.0, nota)


# ─────────────────────────────────────────────────────────────────────────────
# Planilla de estudiantes (mismo formato que registro_notas.py)
# ─────────────────────────────────────────────────────────────────────────────
def leer_lista_estudiantes(ruta_curso):
    archivo = ruta_curso / "estudiantes" / ARCHIVO_LISTA
    if not archivo.exists():
        return []
    from openpyxl import load_workbook
    ws = load_workbook(archivo).active
    nombres = []
    for fila in ws.iter_rows(min_row=2, values_only=True):
        if len(fila) > 2 and fila[2] and str(fila[2]).strip():
            nombres.append(str(fila[2]).strip())
    return nombres


def guardar_lista_estudiantes(ruta_curso, nombres):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    carpeta = ruta_curso / "estudiantes"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / ARCHIVO_LISTA
    wb = Workbook()
    ws = wb.active
    ws.title = "Estudiantes"
    ws.append(["N° Lista", "Código", "Nombre"])
    for c in range(1, 4):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", start_color="1F3864")
        cell.alignment = Alignment(horizontal="center")
    for pos, nombre in enumerate(nombres, start=1):
        ws.append([pos, codigo_de(pos), nombre])
        cod = ws.cell(row=pos + 1, column=2)
        cod.number_format = "@"
        cod.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 34
    wb.save(archivo)
    return archivo


def _openpyxl_disponible():
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


def importar_planilla(ruta_archivo):
    """
    Lee los nombres de los estudiantes desde un archivo .xlsx o .csv.
    - Si hay una columna con encabezado que contenga 'nombre', usa esa.
    - Si no, usa la columna con más texto (nombres).
    Devuelve una lista de nombres (en orden de aparición).
    """
    ruta = Path(ruta_archivo)
    ext = ruta.suffix.lower()
    filas = []
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        ws = load_workbook(ruta, data_only=True).active
        filas = [list(r) for r in ws.iter_rows(values_only=True)]
    elif ext == ".csv":
        import csv as _csv
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            filas = [row for row in _csv.reader(f)]
    else:
        return []

    filas = [f for f in filas if f and any(c not in (None, "") for c in f)]
    if not filas:
        return []

    # Buscar columna por encabezado "nombre"
    encabezado = [str(c).strip().lower() if c is not None else "" for c in filas[0]]
    col = next((i for i, h in enumerate(encabezado) if "nombre" in h), None)
    inicio = 1 if col is not None else 0

    if col is None:
        # Sin encabezado claro: columna con más texto no numérico
        ncols = max(len(f) for f in filas)
        mejor, mejor_count = 0, -1
        for i in range(ncols):
            count = sum(1 for f in filas
                        if i < len(f) and isinstance(f[i], str)
                        and f[i].strip() and not f[i].strip().isdigit())
            if count > mejor_count:
                mejor, mejor_count = i, count
        col = mejor

    nombres = []
    for f in filas[inicio:]:
        if col < len(f) and f[col] is not None:
            v = str(f[col]).strip()
            if v and v.lower() != "nombre":
                nombres.append(v)
    return nombres


def generar_plantilla_estudiantes(carpeta):
    """Crea un Excel-plantilla para que el profesor llene N° de lista + nombres
    (formato tradicional Apellidos Nombres) y luego lo importe."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    archivo = Path(carpeta) / "plantilla_estudiantes.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Estudiantes"
    azul = PatternFill("solid", start_color="1F3864")
    blanco = Font(bold=True, color="FFFFFF", size=12)
    centro = Alignment(horizontal="center", vertical="center")
    ws.cell(row=1, column=1, value="N\u00b0 Lista")
    ws.cell(row=1, column=2, value="Nombre completo (Apellidos Nombres)")
    for c in (1, 2):
        cell = ws.cell(row=1, column=c)
        cell.fill = azul
        cell.font = blanco
        cell.alignment = centro
    for i in range(1, 41):
        ws.cell(row=i + 1, column=1, value=i).alignment = centro
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 46
    ws.freeze_panes = "A2"

    # Hoja con instrucciones claras
    ins = wb.create_sheet("LÉEME (instrucciones)")
    guia = [
        "CÓMO LLENAR LA PLANILLA DE ESTUDIANTES",
        "",
        "1) Ve a la hoja 'Estudiantes' (pestaña de abajo).",
        "2) Escribe un estudiante por fila en la columna 'Nombre completo'.",
        "3) Usa el formato tradicional: primero APELLIDOS y luego NOMBRES.",
        "      Ejemplo:  Pérez Gómez Juan Carlos",
        "4) El N° de Lista ya viene numerado por orden; puedes agregar más filas.",
        "5) El CÓDIGO de cada alumno (001, 002, 003, ...) lo genera la app sola,",
        "      según el orden de la lista. No tienes que escribirlo.",
        "6) Guarda este archivo (Excel) y vuelve a la app:",
        "      Estudiantes  ->  'Importar lista'  ->  elige este archivo.",
        "7) La app mostrará cada nombre con su código, para que se los des a los alumnos.",
    ]
    for i, linea in enumerate(guia, start=1):
        celda = ins.cell(row=i, column=1, value=linea)
        if i == 1:
            celda.font = Font(bold=True, size=13)
    ins.column_dimensions["A"].width = 80

    wb.save(archivo)
    return archivo


# ─────────────────────────────────────────────────────────────────────────────
# Exámenes (clave JSON + PDF opcional)
# ─────────────────────────────────────────────────────────────────────────────
def listar_examenes(ruta_curso):
    carpeta = ruta_curso / "examenes_claves"
    if not carpeta.exists():
        return []
    out = []
    for f in sorted(carpeta.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            # Las claves viejas no traen formato: todas eran de hoja completa
            formato = LH.obtener(d.get("formato")).clave
            out.append((f, d.get("examen", f.stem), d.get("total_preguntas", "?"), formato))
        except Exception:
            continue
    return out


def guardar_clave(ruta_curso, nombre, cantidad, clave_letras, formato):
    carpeta = ruta_curso / "examenes_claves"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre.replace(" ", "_")
    datos = {"examen": nombre, "total_preguntas": cantidad,
             "clave_correctas": clave_letras, "formato": LH.obtener(formato).clave}
    archivo = carpeta / f"respuestas_{nombre}.json"
    archivo.write_text(json.dumps(datos, indent=4, ensure_ascii=False), encoding="utf-8")
    return archivo


def generar_pdf_a_descargas(nombre, cantidad, formato="carta"):
    """Genera la hoja PDF y la deja en Descargas. Devuelve (texto, referencia,
    nombre_archivo); la referencia sirve para abrirla o compartirla."""
    import generador_pdf as GP  # importación tardía
    nombre_arch = f"{nombre.replace(' ', '_')}_hoja.pdf"
    tmp = Path(tempfile.mkdtemp(prefix="hoja_")) / nombre_arch
    GP.generar_hoja_omr(tmp, cantidad, formato)
    texto, ref = PF.guardar_en_descargas(tmp, nombre_arch)
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return texto, ref, nombre_arch


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: CONFIGURACIÓN INICIAL
# ─────────────────────────────────────────────────────────────────────────────
class SetupScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        root.add_widget(Portada("¡Hola!",
                                "Preparemos tu espacio. Solo toma un minuto."))

        tarjeta = Tarjeta(padding=[dp(16), dp(14)], spacing=dp(8))
        tarjeta.add_widget(_caption("¿Cómo te llamas?"))
        self.in_nombre = TextInput(hint_text="Tu nombre y apellido", multiline=False,
                                   size_hint_y=None, height=dp(50))
        tarjeta.add_widget(self.in_nombre)
        tarjeta.add_widget(Widget(size_hint_y=None, height=dp(4)))
        tarjeta.add_widget(_caption("¿Qué grados tienes? Indica cuántos cursos hay en cada uno"))
        self.filas_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                   spacing=dp(8))
        self.filas_box.bind(minimum_height=self.filas_box.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.filas_box)
        tarjeta.add_widget(scroll)

        self.filas = []
        self._agregar_fila()

        btn_add = Factory.BotonSuave(text="+  Agregar otro grado", size_hint_y=None,
                                     height=dp(46))
        btn_add.bind(on_release=lambda *_: self._agregar_fila())
        tarjeta.add_widget(btn_add)
        root.add_widget(tarjeta)

        btn_crear = Factory.BotonAccion(text="Empezar", size_hint_y=None,
                                        height=dp(54))
        btn_crear.bind(on_release=self._crear)
        root.add_widget(btn_crear)
        self.add_widget(root)

    def _agregar_fila(self):
        fila = BoxLayout(size_hint_y=None, height=dp(74), spacing=dp(12))

        col_g = BoxLayout(orientation="vertical", spacing=dp(4))
        col_g.add_widget(_caption("Grado"))
        in_grado = TextInput(hint_text="Ej.: 11", multiline=False, input_filter="int",
                             size_hint_y=None, height=dp(48))
        col_g.add_widget(in_grado)

        col_c = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.55)
        col_c.add_widget(_caption("Cursos (A, B…)"))
        sp = Spinner(text="1", values=[str(i) for i in range(1, 11)],
                     size_hint_y=None, height=dp(48))
        col_c.add_widget(sp)

        fila.add_widget(col_g)
        fila.add_widget(col_c)
        self.filas_box.add_widget(fila)
        self.filas.append((in_grado, sp))

    def _crear(self, *_):
        nombre = self.in_nombre.text.strip()
        if not nombre:
            aviso("¿Cómo te llamas?", "Escribe tu nombre para poder continuar.")
            return
        grados_cursos = []
        for in_grado, sp in self.filas:
            g = in_grado.text.strip()
            if g:
                grados_cursos.append((g, int(sp.text)))
        if not grados_cursos:
            aviso("Falta un grado", "Escribe al menos un grado (por ejemplo, 11) "
                  "y cuántos cursos tiene.")
            return
        GS.inicializar_sistema()
        ruta_prof = GS.crear_profesor(nombre)
        for grado, n in grados_cursos:
            ruta_grado = GS.crear_grado(ruta_prof, grado)
            for i in range(n):
                GS.crear_curso(ruta_grado, chr(65 + i))
        App.get_running_app().ir_a_home()


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: MENÚ PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
class HomeScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.contenedor = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        self.add_widget(self.contenedor)

    def on_pre_enter(self, *_):
        self.construir()

    def construir(self):
        self.contenedor.clear_widgets()
        b = self.contenedor

        profesores = _subdirs(BASE)
        primero = profesores[0] if profesores else ""
        nombre = primero.replace("_", " ").split(" ")[0] if primero else ""
        b.add_widget(Portada(f"Hola, {nombre}" if nombre else "¡Hola!",
                             "¿Con qué curso vas a trabajar hoy?"))

        tarjeta = Tarjeta(size_hint_y=None, padding=[dp(16), dp(14)], spacing=dp(8))
        tarjeta.bind(minimum_height=tarjeta.setter("height"))
        self.sp_prof = Spinner(text=primero, values=profesores,
                               size_hint_y=None, height=dp(48))
        self.sp_prof.bind(text=lambda *_: self._refrescar_grados())
        # Solo se pregunta por el docente si en este celular hay más de uno
        if len(profesores) > 1:
            tarjeta.add_widget(_caption("Docente"))
            tarjeta.add_widget(self.sp_prof)

        fila_gc = BoxLayout(size_hint_y=None, height=dp(72), spacing=dp(10))
        col_g = BoxLayout(orientation="vertical", spacing=dp(4))
        col_g.add_widget(_caption("Grado"))
        self.sp_grado = Spinner(text="", values=[], size_hint_y=None, height=dp(48))
        self.sp_grado.bind(text=lambda *_: self._refrescar_cursos())
        col_g.add_widget(self.sp_grado)
        col_c = BoxLayout(orientation="vertical", spacing=dp(4))
        col_c.add_widget(_caption("Curso"))
        self.sp_curso = Spinner(text="", values=[], size_hint_y=None, height=dp(48))
        self.sp_curso.bind(text=lambda *_: self._guardar_seleccion())
        col_c.add_widget(self.sp_curso)
        fila_gc.add_widget(col_g)
        fila_gc.add_widget(col_c)
        tarjeta.add_widget(fila_gc)

        self.lbl_actual = Pildora(text="", size_hint_y=None, height=dp(36))
        tarjeta.add_widget(self.lbl_actual)
        b.add_widget(tarjeta)

        b.add_widget(Widget())  # espacio flexible: empuja el botón principal abajo

        btn_cal = Factory.BotonAccion(text="Entrar al curso", size_hint_y=None,
                                      height=dp(54))
        btn_cal.bind(on_release=lambda *_: self._entrar())
        b.add_widget(btn_cal)

        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        btn_add = Factory.BotonOutline(text="+  Agregar grado")
        btn_add.bind(on_release=lambda *_: self._popup_agregar())
        fila.add_widget(btn_add)
        btn_edit = Factory.BotonOutline(text="Organizar")
        btn_edit.bind(on_release=lambda *_: self._popup_editar())
        fila.add_widget(btn_edit)
        b.add_widget(fila)

        btn_resp = Factory.BotonTexto(text="Copia de seguridad", size_hint_y=None,
                                      height=dp(40), font_size="14sp")
        btn_resp.bind(on_release=lambda *_: self._popup_respaldo())
        b.add_widget(btn_resp)

        self._refrescar_grados()

    # ── Copia de seguridad ──────────────────────────────────────────────────
    def _popup_respaldo(self):
        _popup_texto(
            "Copia de seguridad",
            "Guardamos todo (listas, exámenes, notas y fotos) en un solo archivo "
            "en tu carpeta de Descargas.\n\nSúbelo a Drive o envíatelo: si cambias "
            "de celular o reinstalas la app, con ese archivo recuperas todo.",
            [("Crear copia", "accion", self._guardar_respaldo),
             ("Restaurar", "normal", self._elegir_respaldo),
             ("Ahora no", "outline", None)], alto=0.52)

    def _guardar_respaldo(self):
        def trabajo():
            zip_path = PF.crear_respaldo(BASE)
            try:
                return PF.guardar_en_descargas(zip_path, zip_path.name) + (zip_path.name,)
            finally:
                zip_path.unlink()

        def listo(res, err):
            if err:
                aviso("No pudimos crear la copia", str(err))
                return
            texto, ref, nombre = res
            aviso_archivo("Tu copia está lista",
                          f"La encuentras en:\n{texto}\n\nTe recomendamos subirla a Drive "
                          "o enviártela, para tenerla fuera del celular.", ref, nombre)
        en_segundo_plano("Guardando tu copia\u2026", trabajo, listo)

    def _elegir_respaldo(self):
        PF.elegir_archivos(self._respaldo_elegido, tipo="zip", multiple=False,
                           titulo="Elige tu copia de seguridad (.zip)")

    def _respaldo_elegido(self, refs):
        nombre = PF.nombre_de(refs[0])
        if not nombre.lower().endswith(".zip"):
            aviso("Ese archivo no sirve", f"'{nombre}' no es una copia de seguridad "
                  "de la app (debe ser un archivo .zip).")
            return

        def trabajo():
            zip_local = PF.copiar_a_temporal(refs[0])
            try:
                return PF.restaurar_respaldo(zip_local, BASE)
            finally:
                shutil.rmtree(zip_local.parent, ignore_errors=True)

        def listo(anterior, err):
            if err:
                aviso("No pudimos restaurar la copia", str(err))
                return
            App.get_running_app().ruta_curso = None
            self.construir()
            aviso("¡Todo de vuelta!",
                  "Recuperamos tus datos de la copia.\n\n"
                  f"Lo que había antes no se perdió: quedó guardado aparte ({anterior.name}).")

        confirmar("¿Restaurar esta copia?",
                  f"Tus datos actuales se cambiarán por los de '{nombre}'.\n\n"
                  "No te preocupes: lo que hay ahora queda guardado aparte, por si acaso.",
                  "Sí, restaurar", lambda: en_segundo_plano("Restaurando tu copia\u2026",
                                                            trabajo, listo), peligro=False)

    def _entrar(self):
        app = App.get_running_app()
        if app.ruta_curso is None:
            aviso("Elige un curso", "Primero escoge el grado y el curso con el que "
                  "vas a trabajar.")
            return
        app.sm.current = "dashboard"

    def _refrescar_grados(self):
        prof = self.sp_prof.text
        grados = _subdirs(BASE / prof) if prof else []
        self.sp_grado.values = grados
        self.sp_grado.text = grados[0] if grados else ""
        self._refrescar_cursos()

    def _refrescar_cursos(self):
        prof, grado = self.sp_prof.text, self.sp_grado.text
        cursos = _subdirs(BASE / prof / grado) if (prof and grado) else []
        self.sp_curso.values = cursos
        self.sp_curso.text = cursos[0] if cursos else ""
        self._guardar_seleccion()

    def _guardar_seleccion(self):
        app = App.get_running_app()
        app.profesor = self.sp_prof.text
        app.grado = self.sp_grado.text
        app.curso = self.sp_curso.text
        if app.profesor and app.grado and app.curso:
            app.ruta_curso = BASE / app.profesor / app.grado / app.curso
            self.lbl_actual.text = f"Vas a trabajar con [b]{app.grado}°{app.curso}[/b]"
        else:
            app.ruta_curso = None
            self.lbl_actual.text = "Escoge un grado y un curso"

    def _popup_agregar(self):
        cont = BoxLayout(orientation="vertical", spacing=dp(6), padding=[dp(8), dp(10)])
        lbl = Label(text="Si el grado ya existe, le sumamos los cursos nuevos.",
                    size_hint_y=None, height=dp(36), font_size="13sp", color=GRIS,
                    halign="left", valign="middle")
        cont.add_widget(_ajustar_texto(lbl))
        cont.add_widget(_caption("Grado"))
        in_g = TextInput(hint_text="Ej.: 10", multiline=False, input_filter="int",
                         size_hint_y=None, height=dp(48))
        cont.add_widget(in_g)
        cont.add_widget(_caption("¿Cuántos cursos?"))
        sp = Spinner(text="1", values=[str(i) for i in range(1, 11)],
                     size_hint_y=None, height=dp(48))
        cont.add_widget(sp)
        cont.add_widget(Widget())
        btn = Factory.BotonAccion(text="Agregar", size_hint_y=None, height=dp(50))
        cont.add_widget(btn)
        pop = Popup(title="Agregar un grado", content=cont, size_hint=(0.9, 0.62))

        def _crear(*_):
            g = in_g.text.strip()
            if not g:
                return
            ruta_prof = BASE / self.sp_prof.text
            ruta_grado = GS.crear_grado(ruta_prof, g)
            inicio = len(_subdirs(ruta_grado))
            for i in range(int(sp.text)):
                GS.crear_curso(ruta_grado, chr(65 + inicio + i))
            pop.dismiss()
            self.construir()

        btn.bind(on_release=_crear)
        pop.open()

    def _popup_editar(self):
        prof_dir = BASE / self.sp_prof.text
        grados = _subdirs(prof_dir)
        cont = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(6), dp(10)])
        cont.add_widget(_ajustar_texto(Label(
            text="Quita los grados o cursos que ya no uses. Siempre te preguntaremos "
                 "antes de borrar algo.",
            size_hint_y=None, height=dp(40), font_size="13sp", color=GRIS,
            halign="left", valign="middle")))
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        inner.bind(minimum_height=inner.setter("height"))
        if not grados:
            inner.add_widget(_vacio("Todavía no hay grados"))
        for grado in grados:
            fg = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8),
                           padding=[0, dp(6), 0, 0])
            lg = Label(text=f"[b]Grado {grado}[/b]", markup=True, font_size="16sp",
                       halign="left", valign="middle")
            fg.add_widget(_ajustar_texto(lg))
            bg = Factory.BotonOutline(text="Borrar grado", size_hint_x=None,
                                      width=dp(124), font_size="13.5sp",
                                      color=(0.776, 0.157, 0.157, 1))
            bg.bind(on_release=lambda inst, gr=grado: self._eliminar_grado(gr))
            fg.add_widget(bg)
            inner.add_widget(fg)
            for curso in _subdirs(prof_dir / grado):
                fc = Tarjeta(orientation="horizontal", size_hint_y=None, height=dp(52),
                             padding=[dp(14), dp(4), dp(4), dp(4)], spacing=dp(6),
                             radio=dp(12), sombra=False)
                lc = Label(text=f"Curso {grado}\u00b0{curso}", halign="left",
                           valign="middle")
                fc.add_widget(_ajustar_texto(lc))
                bc = BotonIcono("borrar", peligro=True)
                bc.bind(on_release=lambda inst, gr=grado, cu=curso:
                        self._eliminar_curso(gr, cu))
                fc.add_widget(bc)
                inner.add_widget(fc)
        scroll = ScrollView()
        scroll.add_widget(inner)
        cont.add_widget(scroll)
        btn_cerrar = Factory.BotonSuave(text="Listo", size_hint_y=None, height=dp(48))
        cont.add_widget(btn_cerrar)
        self._pop_editar = Popup(title="Organizar grados y cursos", content=cont,
                                 size_hint=(0.95, 0.85))
        btn_cerrar.bind(on_release=self._pop_editar.dismiss)
        self._pop_editar.open()

    def _eliminar_ruta(self, ruta, listo):
        try:
            shutil.rmtree(ruta)
        except Exception as e:
            aviso("No pudimos borrarlo", str(e))
            return
        try:
            self._pop_editar.dismiss()
        except Exception:
            pass
        App.get_running_app().ruta_curso = None
        self.construir()
        aviso("Hecho", listo)

    def _eliminar_grado(self, grado):
        confirmar(f"¿Borrar el grado {grado}?",
                  f"Se borrarán todos sus cursos, con sus estudiantes, exámenes y "
                  "notas. Esto no se puede deshacer.\n\n"
                  "Si quieres conservar algo, crea antes una copia de seguridad.",
                  "Sí, borrar", lambda: self._eliminar_ruta(
                      BASE / self.sp_prof.text / grado,
                      f"Borramos el grado {grado} y todos sus cursos."))

    def _eliminar_curso(self, grado, curso):
        confirmar(f"¿Borrar {grado}\u00b0{curso}?",
                  "Se borrarán sus estudiantes, exámenes y notas. "
                  "Esto no se puede deshacer.",
                  "Sí, borrar", lambda: self._eliminar_ruta(
                      BASE / self.sp_prof.text / grado / curso,
                      f"Borramos el curso {grado}\u00b0{curso}."))


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: PANEL DEL CURSO (Dashboard)
# ─────────────────────────────────────────────────────────────────────────────
class DashboardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.contenedor = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        self.add_widget(self.contenedor)

    def on_pre_enter(self, *_):
        self.construir()

    def construir(self):
        app = App.get_running_app()
        b = self.contenedor
        b.clear_widgets()
        b.add_widget(Encabezado(f"Curso {app.grado}°{app.curso}",
                                f"Liceo Sahagún  ·  {app.profesor.replace('_', ' ')}"))
        b.add_widget(_caption("¿Qué quieres hacer?"))

        acciones = (
            ("estudiantes", "Estudiantes", "Tu lista del curso y el código de cada uno",
             "estudiantes"),
            ("examenes", "Exámenes", "Crea un examen y descarga la hoja para imprimir",
             "examenes"),
            ("calificar", "Calificar", "Toma fotos de las hojas y obtén las notas al instante",
             "calificar"),
            ("registro", "Notas", "Planilla de Excel, estadísticas y envío al coordinador",
             "registro"),
        )
        for icono, titulo, detalle, destino in acciones:
            btn = BotonMenu(icono=icono, titulo=titulo, detalle=detalle)
            btn.bind(on_release=lambda inst, d=destino: self._ir(d))
            b.add_widget(btn)

        b.add_widget(Widget())  # espacio flexible
        b.add_widget(_boton_volver("Cambiar de curso", "home"))

    def _ir(self, pantalla):
        app = App.get_running_app()
        if app.ruta_curso is None:
            aviso("Elige un curso", "Vuelve al inicio y escoge el grado y el curso.")
            return
        app.sm.current = pantalla


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: ESTUDIANTES
# ─────────────────────────────────────────────────────────────────────────────
class EstudiantesScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)

    def on_pre_enter(self, *_):
        self.construir()

    def construir(self):
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Estudiantes", f"Curso {app.grado}°{app.curso}"))
        if not _openpyxl_disponible():
            b.add_widget(_vacio("Falta un componente",
                                "Instala la librería 'openpyxl' (pip install openpyxl)."))
            self._boton_volver(b)
            return
        nombres = leer_lista_estudiantes(app.ruta_curso)
        b.add_widget(_caption(f"{len(nombres)} estudiantes  ·  toca un nombre para cambiarlo"
                              if nombres else "Tu lista del curso"))
        lista_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6),
                              padding=[0, 0, 0, dp(4)])
        lista_box.bind(minimum_height=lista_box.setter("height"))
        if nombres:
            for pos, nombre in enumerate(nombres, start=1):
                fila = Factory.FilaLista(
                    text=f"[color={GRIS_HEX}][b]{codigo_de(pos)}[/b][/color]     {nombre}",
                    size_hint_y=None, height=dp(48))
                fila.bind(on_release=lambda inst, p=pos: self._editar(p))
                lista_box.add_widget(fila)
        else:
            lista_box.add_widget(_vacio(
                "Todavía no hay estudiantes",
                "Escríbelos abajo uno por uno, o importa tu lista de Excel. "
                "A cada uno le damos un código según su orden (001, 002…).", alto=150))
        scroll = ScrollView()
        scroll.add_widget(lista_box)
        b.add_widget(scroll)
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.in_nombre = TextInput(hint_text="Nombre del estudiante", multiline=False)
        self.in_nombre.bind(on_text_validate=self._agregar)
        fila.add_widget(self.in_nombre)
        btn_add = Button(text="Agregar", size_hint_x=None, width=dp(104))
        btn_add.bind(on_release=self._agregar)
        fila.add_widget(btn_add)
        b.add_widget(fila)
        fila2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        btn_importar = Factory.BotonOutline(text="Importar lista", font_size="14sp")
        btn_importar.bind(on_release=self._importar)
        fila2.add_widget(btn_importar)
        btn_plantilla = Factory.BotonOutline(text="Plantilla Excel", font_size="14sp")
        btn_plantilla.bind(on_release=self._descargar_plantilla)
        fila2.add_widget(btn_plantilla)
        if nombres:
            btn_vaciar = BotonIcono("borrar", peligro=True, size=(dp(46), dp(46)))
            btn_vaciar.bind(on_release=self._vaciar)
            fila2.add_widget(btn_vaciar)
        b.add_widget(fila2)
        self._boton_volver(b)

    def _boton_volver(self, b):
        b.add_widget(_boton_volver("Volver al curso", "dashboard"))

    def _agregar(self, *_):
        app = App.get_running_app()
        nombre = self.in_nombre.text.strip()
        if not nombre:
            return
        nombres = leer_lista_estudiantes(app.ruta_curso)
        nombres.append(nombre)
        guardar_lista_estudiantes(app.ruta_curso, nombres)
        self.construir()

    def _editar(self, pos):
        """Editar el nombre o eliminar al estudiante de la posición 'pos' (1-based)."""
        app = App.get_running_app()
        nombres = leer_lista_estudiantes(app.ruta_curso)
        if not 1 <= pos <= len(nombres):
            return
        cont = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(8), dp(10)])
        cont.add_widget(_caption(f"Nombre  ·  código {codigo_de(pos)}"))
        ti = TextInput(text=nombres[pos - 1], multiline=False, size_hint_y=None, height=dp(48))
        cont.add_widget(ti)
        cont.add_widget(Widget())
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_borrar = BotonIcono("borrar", peligro=True, size=(dp(48), dp(48)))
        btn_ok = Factory.BotonAccion(text="Guardar cambios")
        fila.add_widget(btn_borrar)
        fila.add_widget(btn_ok)
        cont.add_widget(fila)
        pop = Popup(title="Estudiante", content=cont, size_hint=(0.9, 0.42))

        def _guardar(*_):
            nuevo = ti.text.strip()
            if nuevo:
                nombres[pos - 1] = nuevo
                guardar_lista_estudiantes(app.ruta_curso, nombres)
            pop.dismiss()
            self.construir()

        def _eliminar():
            del nombres[pos - 1]
            guardar_lista_estudiantes(app.ruta_curso, nombres)
            self.construir()

        def _pedir_confirmacion(*_):
            pop.dismiss()
            siguientes = len(nombres) - pos
            extra = (f"\n\nOjo: los {siguientes} que siguen en la lista cambiarán de "
                     f"código (el {codigo_de(pos + 1)} pasa a ser {codigo_de(pos)}, y así). "
                     "Si ya calificaste exámenes, algunas hojas podrían quedar con otro estudiante."
                     if siguientes else "")
            confirmar(f"¿Quitar a {nombres[pos - 1]}?",
                      f"Saldrá de la lista del curso.{extra}",
                      "Sí, quitar", _eliminar)

        btn_ok.bind(on_release=_guardar)
        ti.bind(on_text_validate=_guardar)
        btn_borrar.bind(on_release=_pedir_confirmacion)
        pop.open()

    def _descargar_plantilla(self, *_):
        def trabajo():
            tmp = Path(tempfile.mkdtemp(prefix="plantilla_"))
            try:
                ruta = generar_plantilla_estudiantes(tmp)
                return PF.guardar_en_descargas(ruta, ruta.name) + (ruta.name,)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def listo(res, err):
            if err:
                aviso("No pudimos crear la plantilla", str(err))
                return
            texto, ref, nombre = res
            aviso_archivo("Tu plantilla está lista",
                          f"La encuentras en:\n{texto}\n\nLlénala en Excel o Google Sheets "
                          "y luego usa 'Importar lista'.", ref, nombre)
        en_segundo_plano("Preparando la plantilla\u2026", trabajo, listo)

    def _vaciar(self, *_):
        app = App.get_running_app()
        n = len(leer_lista_estudiantes(app.ruta_curso))
        if not n:
            return

        def _hacer():
            guardar_lista_estudiantes(app.ruta_curso, [])
            self.construir()
        confirmar("¿Vaciar la lista?", f"Quitaremos a los {n} estudiantes de este curso.",
                  "Sí, vaciar", _hacer)

    def _importar(self, *_):
        PF.elegir_archivos(self._planilla_elegida, tipo="planillas", multiple=False,
                           titulo="Elige tu lista (Excel o CSV)")

    def _planilla_elegida(self, refs):
        app = App.get_running_app()
        nombre = PF.nombre_de(refs[0])
        if Path(nombre).suffix.lower() not in (".xlsx", ".xlsm", ".csv"):
            aviso("Ese archivo no sirve", f"'{nombre}' no es un Excel (.xlsx) ni un CSV.\n\n"
                  "Si tu lista está en Google Sheets, descárgala como .xlsx y vuelve a intentarlo.")
            return
        try:
            nombres = importar_planilla(PF.copiar_a_temporal(refs[0]))
        except Exception as e:
            aviso("No pudimos leer el archivo", str(e))
            return
        if not nombres:
            aviso("No encontramos nombres", "El archivo necesita una columna con los "
                  "nombres de los estudiantes.")
            return

        def _hacer():
            guardar_lista_estudiantes(app.ruta_curso, nombres)
            self.construir()
            aviso("¡Lista importada!", f"Agregamos {len(nombres)} estudiantes al curso.")

        actuales = len(leer_lista_estudiantes(app.ruta_curso))
        if actuales:
            confirmar("¿Cambiar la lista actual?",
                      f"El archivo trae {len(nombres)} estudiantes y reemplazará a los "
                      f"{actuales} que tienes ahora. Los códigos siguen el orden del archivo.",
                      "Sí, cambiarla", _hacer, peligro=False)
        else:
            _hacer()

# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: EXÁMENES (Paso 3)
# ─────────────────────────────────────────────────────────────────────────────
class ExamenesScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)

    def on_pre_enter(self, *_):
        self.construir()

    def construir(self):
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Exámenes", f"Curso {app.grado}°{app.curso}"))
        examenes = listar_examenes(app.ruta_curso)
        lista_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8),
                              padding=[0, dp(2), 0, dp(6)])
        lista_box.bind(minimum_height=lista_box.setter("height"))
        if examenes:
            b.add_widget(_caption(f"{len(examenes)} {'exámenes' if len(examenes) != 1 else 'examen'}"
                                  "  ·  descarga la hoja cuando la necesites"))
            for ruta, nombre, npreg, formato in examenes:
                fila = Tarjeta(orientation="horizontal", size_hint_y=None, height=dp(70),
                               padding=[dp(16), dp(12), dp(12), dp(12)], spacing=dp(8))
                tipo = "media hoja" if formato == LH.MEDIA_CARTA.clave else "hoja completa"
                lbl = Label(
                    text=f"[b]{nombre.replace('_', ' ')}[/b]\n[size=12.5sp][color={GRIS_HEX}]"
                         f"{npreg} preguntas · {tipo}[/color][/size]",
                    markup=True, halign="left", valign="middle", line_height=1.15,
                    max_lines=2)
                fila.add_widget(_ajustar_texto(lbl))
                btn_dl = BotonIcono("descargar")
                btn_dl.bind(on_release=lambda inst, n=nombre, q=npreg, f=formato:
                            self._descargar(n, q, f))
                fila.add_widget(btn_dl)
                btn_x = BotonIcono("borrar", peligro=True)
                btn_x.bind(on_release=lambda inst, r=ruta: self._borrar(r))
                fila.add_widget(btn_x)
                lista_box.add_widget(fila)
        else:
            lista_box.add_widget(_vacio(
                "Todavía no hay exámenes",
                "Crea el primero: le pones nombre, marcas las respuestas correctas "
                "y te damos la hoja lista para imprimir.", alto=160))
        scroll = ScrollView()
        scroll.add_widget(lista_box)
        b.add_widget(scroll)
        btn_nuevo = Factory.BotonAccion(text="+  Nuevo examen", size_hint_y=None,
                                        height=dp(54))
        btn_nuevo.bind(on_release=lambda *_: self._popup_nuevo())
        b.add_widget(btn_nuevo)
        b.add_widget(_boton_volver("Volver al curso", "dashboard"))

    def _borrar(self, ruta):
        try:
            nombre = json.loads(ruta.read_text(encoding="utf-8")).get("examen", ruta.stem)
        except Exception:
            nombre = ruta.stem

        def _hacer():
            try:
                ruta.unlink()
            except Exception:
                pass
            self.construir()
        confirmar("¿Borrar este examen?",
                  f"Se borrará '{nombre.replace('_', ' ')}' con sus respuestas correctas.\n\n"
                  "Las notas que ya calificaste se conservan.", "Sí, borrar", _hacer)

    def _descargar(self, nombre, npreg, formato):
        try:
            cantidad = int(npreg)
        except (ValueError, TypeError):
            aviso("Algo no cuadra", "Ese examen no tiene un número de preguntas válido.")
            return

        def listo(res, err):
            if err:
                aviso("No pudimos crear la hoja", str(err))
                return
            texto, ref, arch = res
            aviso_archivo("Tu hoja está lista", f"La encuentras en:\n{texto}", ref, arch)
        en_segundo_plano("Preparando la hoja\u2026",
                         lambda: generar_pdf_a_descargas(nombre, cantidad, formato), listo)

    def _popup_nuevo(self):
        cont = BoxLayout(orientation="vertical", spacing=dp(6), padding=[dp(8), dp(10)])
        cont.add_widget(_caption("¿Cómo se llama?"))
        in_nombre = TextInput(hint_text="Ej.: Inglés primer parcial", multiline=False,
                              size_hint_y=None, height=dp(48))
        cont.add_widget(in_nombre)
        cont.add_widget(_caption("¿Cuántas preguntas tiene?"))
        in_num = TextInput(hint_text="Ej.: 20", multiline=False, input_filter="int",
                           size_hint_y=None, height=dp(48))
        cont.add_widget(in_num)
        cont.add_widget(_caption("Tamaño de la hoja"))
        formatos = {f.descripcion: f for f in (LH.MEDIA_CARTA, LH.CARTA)}
        sp_formato = Spinner(text=LH.MEDIA_CARTA.descripcion, values=list(formatos),
                             size_hint_y=None, height=dp(48))
        cont.add_widget(sp_formato)

        def _sugerir_formato(_inst, texto):
            # Si no cabe en media hoja, pasar solo a hoja completa
            try:
                n = int(texto)
            except ValueError:
                return
            if n > LH.MEDIA_CARTA.max_preguntas:
                sp_formato.text = LH.CARTA.descripcion
        in_num.bind(text=_sugerir_formato)
        lbl_msg = Label(text="", size_hint_y=None, height=dp(24), font_size="13sp",
                        color=(0.776, 0.157, 0.157, 1))
        cont.add_widget(lbl_msg)
        cont.add_widget(Widget())
        btn_generar = Factory.BotonAccion(text="Siguiente: marcar respuestas",
                                          size_hint_y=None, height=dp(50))
        cont.add_widget(btn_generar)
        pop = Popup(title="Nuevo examen", content=cont, size_hint=(0.92, 0.74))

        def _generar(*_):
            app = App.get_running_app()
            nombre = in_nombre.text.strip()
            if not nombre:
                lbl_msg.text = "Ponle un nombre al examen."
                return
            try:
                cantidad = int(in_num.text)
            except ValueError:
                lbl_msg.text = "Escribe cuántas preguntas tiene."
                return
            formato = formatos[sp_formato.text]
            if not (1 <= cantidad <= formato.max_preguntas):
                lbl_msg.text = (f"En {formato.descripcion.split(' (')[0].lower()} caben "
                                f"de 1 a {formato.max_preguntas} preguntas.")
                return

            def _ir():
                pop.dismiss()
                app.sm.get_screen("claves").preparar(nombre, cantidad, formato.clave)
                app.sm.current = "claves"

            existente = (app.ruta_curso / "examenes_claves"
                         / f"respuestas_{nombre.replace(' ', '_')}.json")
            if existente.exists():
                confirmar("Ese nombre ya existe",
                          f"Ya tienes un examen llamado '{nombre}'.\n\n"
                          "Si sigues, cambiarás sus respuestas correctas por las nuevas.",
                          "Seguir", _ir, peligro=False)
            else:
                _ir()

        btn_generar.bind(on_release=_generar)
        pop.open()


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: RESPUESTAS CORRECTAS  ·  botones A/B/C/D por pregunta
# ─────────────────────────────────────────────────────────────────────────────
def _nombre_curso(grado, curso):
    return f"{grado}°{curso}"


def _enumerar(cosas):
    """['a', 'b', 'c'] -> 'a, b y c'"""
    cosas = list(cosas)
    if len(cosas) <= 1:
        return "".join(cosas)
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


class OpcionLetra(Button):
    """Botón de una letra (A, B, C o D); azul cuando está elegido."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.radio = dp(10)
        self.marcar(False)

    def marcar(self, elegido):
        if elegido:
            self.color = BLANCO
            self.color_fondo = AZUL
            self.color_fondo_down = AZUL_OSC
            self.color_borde = (0, 0, 0, 0)
        else:
            self.color = AZUL
            self.color_fondo = BLANCO
            self.color_fondo_down = TINTE
            self.color_borde = BORDE


class ClavesScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)
        self.nombre = ""
        self.cantidad = 0
        self.formato = LH.MEDIA_CARTA.clave
        self.respuestas = []
        self.botones = []
        self.destinos = set()       # otros cursos donde también se crea: {(grado, curso)}

    def preparar(self, nombre, cantidad, formato):
        self.nombre = nombre
        self.cantidad = int(cantidad)
        self.formato = formato
        # Por defecto, también en los demás cursos del mismo grado
        app = App.get_running_app()
        self.destinos = {(g, c) for g, c in self._otros_cursos() if g == app.grado}

    def on_pre_enter(self, *_):
        self.construir()

    # ── Otros cursos del docente ────────────────────────────────────────────
    def _otros_cursos(self):
        """[(grado, curso)] de todos los cursos del docente, menos el actual."""
        app = App.get_running_app()
        prof = BASE / app.profesor
        return [(g, c) for g in _subdirs(prof) for c in _subdirs(prof / g)
                if (g, c) != (app.grado, app.curso)]

    def construir(self):
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Respuestas correctas", self.nombre.replace("_", " ")))
        tipo = LH.obtener(self.formato).descripcion.split(" (")[0].lower()
        b.add_widget(_caption(f"{self.cantidad} preguntas  ·  {tipo}  ·  "
                              "toca la letra correcta de cada una"))

        n = self.cantidad
        self.respuestas = [None] * (n + 1)   # 1-indexado
        self.botones = [None] * (n + 1)
        lista = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None,
                          padding=[0, 0, 0, dp(6)])
        lista.bind(minimum_height=lista.setter("height"))
        for q in range(1, n + 1):
            fila = Tarjeta(orientation="horizontal", size_hint_y=None, height=dp(58),
                           padding=[dp(10), dp(8)], spacing=dp(8), radio=dp(14),
                           sombra=False)
            etq = Label(text=str(q), size_hint_x=None, width=dp(34), bold=True,
                        color=GRIS, halign="center", valign="middle")
            fila.add_widget(_ajustar_texto(etq))
            grupo = []
            for letra in ("A", "B", "C", "D"):
                btn = OpcionLetra(text=letra)
                btn.bind(on_release=lambda inst, q=q, l=letra: self._elegir(q, l))
                grupo.append(btn)
                fila.add_widget(btn)
            self.botones[q] = grupo
            lista.add_widget(fila)

        scroll = ScrollView(bar_width=dp(3))
        scroll.add_widget(lista)
        b.add_widget(scroll)

        self.lbl_cuenta = Label(size_hint_y=None, height=dp(22), font_size="13.5sp",
                                bold=True, color=AZUL, markup=True)
        b.add_widget(self.lbl_cuenta)
        self._contar()

        opciones = Tarjeta(size_hint_y=None, padding=[dp(14), dp(4)], spacing=0,
                           radio=dp(14), sombra=False)
        opciones.bind(minimum_height=opciones.setter("height"))
        if self._otros_cursos():
            fila_otros = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            self.chk_otros = Casilla(active=bool(self.destinos), height=dp(48))
            self.chk_otros.bind(active=self._al_marcar_otros)
            fila_otros.add_widget(self.chk_otros)
            btn_elegir = Factory.BotonTexto(text="Elegir", size_hint_x=None, width=dp(70),
                                            font_size="14sp", bold=True)
            btn_elegir.bind(on_release=lambda *_: self._elegir_cursos())
            fila_otros.add_widget(btn_elegir)
            opciones.add_widget(fila_otros)
            self._texto_otros()
        else:
            self.chk_otros = None
        self.chk_pdf = Casilla(texto="Descargar también la hoja para imprimir",
                               active=True, height=dp(48))
        opciones.add_widget(self.chk_pdf)
        b.add_widget(opciones)

        fila_btn = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        btn_cancel = Factory.BotonOutline(text="Cancelar", size_hint_x=0.4)
        btn_cancel.bind(on_release=lambda *_: setattr(
            App.get_running_app().sm, "current", "examenes"))
        btn_guardar = Factory.BotonAccion(text="Guardar examen")
        btn_guardar.bind(on_release=self._guardar)
        fila_btn.add_widget(btn_cancel)
        fila_btn.add_widget(btn_guardar)
        b.add_widget(fila_btn)

    def _elegir(self, q, letra):
        self.respuestas[q] = letra
        for btn in self.botones[q]:
            btn.marcar(btn.text == letra)
        self._contar()

    # ── "Crear también en otros cursos" ─────────────────────────────────────
    def _texto_otros(self):
        app = App.get_running_app()
        if self.destinos:
            nombres = [_nombre_curso(g, c) for g, c in sorted(self.destinos)]
            texto = "Crear también en " + _enumerar(nombres)
        elif any(g == app.grado for g, _ in self._otros_cursos()):
            texto = f"Crear también en los otros cursos de {app.grado}°"
        else:
            texto = "Crear también en otros cursos"
        self.chk_otros.lbl.text = texto

    def _al_marcar_otros(self, _chk, activo):
        app = App.get_running_app()
        if activo and not self.destinos:
            mismos = {(g, c) for g, c in self._otros_cursos() if g == app.grado}
            if mismos:
                self.destinos = mismos
            else:
                self._elegir_cursos()
        elif not activo:
            self.destinos = set()
        self._texto_otros()

    def _elegir_cursos(self):
        """Ventana con una casilla por cada curso del docente."""
        app = App.get_running_app()
        cont = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(8), dp(10)])
        cont.add_widget(_ajustar_texto(Label(
            text="Guardaremos el mismo examen, con las mismas respuestas, en los cursos "
                 "que marques. Así no tienes que repetirlo.",
            size_hint_y=None, height=dp(56), font_size="13sp", color=GRIS,
            halign="left", valign="middle")))
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        inner.bind(minimum_height=inner.setter("height"))
        casillas = {}
        grado_previo = None
        for g, c in self._otros_cursos():
            if g != grado_previo:
                inner.add_widget(_caption(f"Grado {g}"))
                grado_previo = g
            chk = Casilla(texto=f"Curso {_nombre_curso(g, c)}",
                          active=(g, c) in self.destinos)
            casillas[(g, c)] = chk
            inner.add_widget(chk)
        scroll = ScrollView()
        scroll.add_widget(inner)
        cont.add_widget(scroll)
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_mismo = Factory.BotonOutline(text=f"Solo {app.grado}°", size_hint_x=0.45)
        btn_ok = Factory.BotonAccion(text="Listo")
        fila.add_widget(btn_mismo)
        fila.add_widget(btn_ok)
        cont.add_widget(fila)
        pop = Popup(title="¿En qué otros cursos?", content=cont, size_hint=(0.92, 0.78))

        def _solo_mismo_grado(*_):
            for (g, _c), chk in casillas.items():
                chk.active = g == app.grado

        def _aceptar(*_):
            self.destinos = {k for k, chk in casillas.items() if chk.active}
            pop.dismiss()
            if self.chk_otros is not None:
                self.chk_otros.active = bool(self.destinos)
                self._texto_otros()

        btn_mismo.bind(on_release=_solo_mismo_grado)
        btn_ok.bind(on_release=_aceptar)
        pop.open()

    # ── Guardar ─────────────────────────────────────────────────────────────
    def _faltan(self):
        return [q for q in range(1, self.cantidad + 1) if self.respuestas[q] is None]

    def _contar(self):
        faltan = len(self._faltan())
        hechas = self.cantidad - faltan
        self.lbl_cuenta.text = (f"Llevas {hechas} de {self.cantidad}" if faltan
                                else f"[color={VERDE}]¡Todas las respuestas listas![/color]")

    def _guardar(self, *_):
        app = App.get_running_app()
        faltan = self._faltan()
        if faltan:
            lista = ", ".join(str(q) for q in faltan[:10]) + ("…" if len(faltan) > 10 else "")
            aviso("Te faltan algunas", f"Marca la respuesta correcta de la pregunta"
                  f"{'s' if len(faltan) > 1 else ''}:\n\n{lista}")
            return
        destinos = sorted(self.destinos) if self.chk_otros is not None else []
        nombre_arch = f"respuestas_{self.nombre.replace(' ', '_')}.json"
        ya_existe = [_nombre_curso(g, c) for g, c in destinos
                     if (BASE / app.profesor / g / c / "examenes_claves" / nombre_arch).exists()]
        if ya_existe:
            confirmar("Ese examen ya está en otros cursos",
                      f"'{self.nombre}' ya existe en {_enumerar(ya_existe)}.\n\n"
                      "Si sigues, sus respuestas correctas se cambiarán por estas.",
                      "Seguir", lambda: self._guardar_en(destinos), peligro=False)
        else:
            self._guardar_en(destinos)

    def _guardar_en(self, destinos):
        app = App.get_running_app()
        clave = [self.respuestas[q] for q in range(1, self.cantidad + 1)]
        guardar_clave(app.ruta_curso, self.nombre, self.cantidad, clave, self.formato)
        errores = []
        for g, c in destinos:
            try:
                guardar_clave(BASE / app.profesor / g / c, self.nombre, self.cantidad,
                              clave, self.formato)
            except Exception as e:
                errores.append(f"{_nombre_curso(g, c)} ({e})")
        cursos = [_nombre_curso(app.grado, app.curso)] + [
            _nombre_curso(g, c) for g, c in destinos]
        mensaje = (f"'{self.nombre}' quedó guardado en {_enumerar(cursos)}."
                   if len(cursos) > 1 else
                   f"'{self.nombre}' quedó guardado con sus {self.cantidad} respuestas.")
        if errores:
            mensaje += "\n\nNo pudimos guardarlo en: " + ", ".join(errores)
        app.sm.current = "examenes"
        if self.chk_pdf.active:
            nombre, cantidad, formato = self.nombre, self.cantidad, self.formato

            def listo(res, err):
                if err:
                    aviso("¡Examen guardado!", f"{mensaje}\n\n(La hoja no se pudo crear: {err})")
                    return
                texto, ref, arch = res
                aviso_archivo("¡Examen guardado!",
                              f"{mensaje}\n\nLa hoja para imprimir está en:\n{texto}", ref, arch)
            en_segundo_plano("Preparando la hoja…",
                             lambda: generar_pdf_a_descargas(nombre, cantidad, formato), listo)
        else:
            aviso("¡Examen guardado!", mensaje)


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: CALIFICAR (Paso 4)  ·  digitalizar -> leer -> guardar notas
# ─────────────────────────────────────────────────────────────────────────────
class CalificarScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)
        self.examen = ""
        self.errores = []     # hojas que no se pudieron leer en esta sesión (no se guardan)

    def on_pre_enter(self, *_):
        self.errores = []
        self.construir()

    @property
    def resultados(self):
        """Lo que se muestra: errores de esta sesión + historial guardado del examen."""
        guardados = sorted(self._leer_notas(), key=lambda r: r.get("fecha", ""), reverse=True)
        return self.errores + guardados

    def construir(self):
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Calificar", f"Curso {app.grado}°{app.curso}"))

        examenes = listar_examenes(app.ruta_curso)
        if not examenes:
            b.add_widget(_vacio("Primero necesitas un examen",
                                "Créalo en 'Exámenes' con sus respuestas correctas y "
                                "vuelve aquí para calificar.", alto=150))
            b.add_widget(Widget())
            self._volver(b)
            return

        self._mapa_claves = {nombre: ruta for ruta, nombre, _, _ in examenes}
        nombres = list(self._mapa_claves.keys())
        if self.examen not in nombres:
            self.examen, self.errores = nombres[0], []
        b.add_widget(_caption("Examen"))
        self.sp_examen = Spinner(text=self.examen, values=nombres,
                                 size_hint_y=None, height=dp(48))
        self.sp_examen.bind(text=self._cambiar_examen)
        b.add_widget(self.sp_examen)

        fila_btn = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        btn_cam = Factory.BotonAccion(text="Usar la cámara")
        btn_cam.bind(on_release=self._tomar_foto)
        fila_btn.add_widget(btn_cam)
        btn = Button(text="Desde la galería")
        btn.bind(on_release=self._calificar)
        fila_btn.add_widget(btn)
        b.add_widget(fila_btn)

        lista = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6),
                          padding=[0, 0, 0, dp(6)])
        lista.bind(minimum_height=lista.setter("height"))
        resultados = self.resultados
        if resultados:
            import registro_notas as RN
            # Códigos usados por hojas distintas en TODO el examen
            repetidos = RN.detectar_conflictos(self._leer_notas())
            hojas = len(resultados) - len(self.errores)
            b.add_widget(_caption(f"{hojas} hoja{'s' if hojas != 1 else ''} calificada"
                                  f"{'s' if hojas != 1 else ''}  ·  las más recientes arriba"))
            for r in resultados:
                lista.add_widget(self._fila_resultado(r, repetidos))
        else:
            lista.add_widget(_vacio("Aún no has calificado hojas de este examen",
                                    "Toma una foto de cada hoja (o elígelas de la galería) "
                                    "y aquí verás las notas.", alto=140))
        scroll = ScrollView()
        scroll.add_widget(lista)
        b.add_widget(scroll)

        self._volver(b)

    def _fila_resultado(self, r, repetidos):
        codigo = str(r.get("codigo", "???"))
        if codigo == "ERROR":
            texto = (f"[color={ROJO}][b]No pudimos leerla[/b][/color]\n[size=12.5sp]"
                     f"[color={GRIS_HEX}]{r.get('error') or r['archivo']}[/color][/size]")
        elif not codigo.isdigit():
            texto = (f"[color={AMBAR}][b]Código {codigo}[/b][/color]\n[size=12.5sp]"
                     f"[color={GRIS_HEX}]No se lee bien: tócala para corregirlo[/color][/size]")
        elif codigo in repetidos:
            texto = (f"[color={AMBAR}][b]Código {codigo}[/b][/color]\n[size=12.5sp]"
                     f"[color={GRIS_HEX}]Está repetido: revisa cuál es el correcto"
                     f"[/color][/size]")
        else:
            n = nota_local(r["aciertos"], r["total"])
            col = VERDE if n >= 6.0 else ROJO
            texto = (f"[b]Código {codigo}[/b]   [color={col}][b]{n:.1f}[/b][/color]\n"
                     f"[size=12.5sp][color={GRIS_HEX}]{r['aciertos']} de {r['total']} "
                     f"correctas[/color][/size]")
        fila = Tarjeta(orientation="horizontal", size_hint_y=None, height=dp(64),
                       padding=[dp(16), dp(8), dp(10), dp(8)], spacing=dp(8),
                       radio=dp(14), sombra=False)
        lbl = Label(text=texto, markup=True, halign="left", valign="middle", font_size="15sp",
                    max_lines=2, line_height=1.15)
        lbl.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, i.height)))
        fila.add_widget(lbl)
        btn = Factory.BotonSuave(text="Ver", size_hint=(None, None), size=(dp(64), dp(44)),
                                 font_size="14sp")
        btn.bind(on_release=lambda inst, rr=r: self._ver_hoja(rr))
        fila.add_widget(btn)
        return fila

    def _cambiar_examen(self, _sp, nombre):
        if nombre != self.examen:
            self.examen, self.errores = nombre, []
            self.construir()

    def _volver(self, b):
        b.add_widget(_boton_volver("Volver al curso", "dashboard"))

    def _calificar(self, *_):
        PF.elegir_archivos(lambda refs: self._iniciar_calificacion(refs, mover=False),
                           tipo="imagenes", multiple=True,
                           titulo="Elige las fotos de las hojas")

    def _ver_hoja(self, r):
        """Detalle de una hoja: imagen marcada + corregir código / eliminar."""
        import lector_omr as L
        codigo = str(r.get("codigo", "???"))
        cont = BoxLayout(orientation="vertical", spacing=dp(8), padding=[0, dp(4), 0, 0])
        img = None
        if r.get("imagen"):
            img = L.leer_imagen(self._ruta_notas().parent / r["imagen"])
        if img is not None:
            cont.add_widget(Image(texture=self._np_a_textura(img), allow_stretch=True,
                                  keep_ratio=True))
        else:
            msg = (r.get("error") or "No pudimos leer esta hoja.") if codigo == "ERROR" \
                else "Esta hoja no tiene foto guardada."
            lbl = Label(text=msg, halign="center", valign="middle")
            lbl.bind(size=lambda i, *_: setattr(i, "text_size", (i.width, None)))
            cont.add_widget(lbl)
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        titulo = (f"Código {codigo}  ·  {r['aciertos']} de {r['total']} correctas"
                  if codigo != "ERROR" else r.get("archivo", "Hoja"))
        pop = Popup(title=titulo, content=cont, size_hint=(0.96, 0.92))
        btn_del = BotonIcono("borrar", peligro=True, size=(dp(48), dp(48)))
        btn_del.bind(on_release=lambda *_: (pop.dismiss(), self._eliminar_hoja(r)))
        fila.add_widget(btn_del)
        if codigo != "ERROR":
            btn_cod = Factory.BotonSuave(text="Corregir código", font_size="14sp")
            btn_cod.bind(on_release=lambda *_: (pop.dismiss(), self._editar_codigo(r)))
            fila.add_widget(btn_cod)
        btn_x = Factory.BotonOutline(text="Listo", font_size="14sp", size_hint_x=0.6)
        btn_x.bind(on_release=lambda *_: pop.dismiss())
        fila.add_widget(btn_x)
        cont.add_widget(fila)
        pop.open()

    def _eliminar_hoja(self, r):
        if r.get("codigo") == "ERROR":
            self.errores = [e for e in self.errores if e is not r]
            self.construir()
            return

        def _hacer():
            datos = [e for e in self._leer_notas() if e.get("archivo") != r.get("archivo")]
            self._ruta_notas().write_text(json.dumps(datos, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
            if r.get("imagen"):
                try:
                    (self._ruta_notas().parent / r["imagen"]).unlink()
                except Exception:
                    pass
            self.construir()
        confirmar("¿Quitar esta hoja?",
                  f"Código {r.get('codigo')}  ·  {r['aciertos']} de {r['total']} correctas.\n\n"
                  "Su nota ya no saldrá en la planilla. Úsalo si la foto estaba repetida "
                  "o era de otro examen.", "Sí, quitar", _hacer)

    def _iniciar_calificacion(self, archivos, mover=False, al_terminar=None):
        """
        Califica las fotos EN SEGUNDO PLANO, con una ventana de progreso.

        La interfaz no se congela (en Android así no aparece "La app no
        responde"): un hilo procesa las fotos una por una y avisa a la
        pantalla después de cada una. Cancelar detiene el trabajo al terminar
        la hoja en curso; las hojas ya calificadas se guardan.

        mover=True mueve la foto en vez de copiarla (fotos de la cámara).
        al_terminar(registros): se llama al final en lugar de mostrar el resumen.
        """
        import lector_omr as L
        app = App.get_running_app()
        ruta_curso = app.ruta_curso
        clave_json = self._mapa_claves[self.sp_examen.text]
        try:
            datos = L.cargar_datos_examen(clave_json)
        except Exception as e:
            aviso("Hay un problema con este examen",
                  f"No pudimos leer sus respuestas correctas:\n{e}")
            return

        cancelar = threading.Event()
        pop = PopupProgreso(
            "Calificando hojas" if len(archivos) > 1 else "Calificando la hoja",
            f"{datos.nombre.replace('_', ' ')}  ·  {app.grado}°{app.curso}",
            len(archivos), cancelar.set)
        pop.open()

        dir_crudos = ruta_curso / "examenes_crudos"
        dir_crudos.mkdir(parents=True, exist_ok=True)

        def estado_de(r):
            if r["codigo"] == "ERROR":
                return "error"
            return "ok" if str(r["codigo"]).isdigit() else "revisar"

        def trabajo():
            nuevos = []
            for i, a in enumerate(archivos):
                if cancelar.is_set():
                    break
                try:
                    nombre = PF.nombre_de(a)
                except Exception:
                    nombre = "foto"
                Clock.schedule_once(lambda dt, i=i, n=nombre: pop.empezar(i, n))
                # Copiar con nombre único (dos 'IMG_0001.jpg' ya no se pisan)
                # y calificar SOLO esa foto
                destino = dir_crudos / L.nombre_unico(nombre)
                try:
                    PF.copiar(a, destino, mover=mover)
                    r = L.calificar_foto(destino, clave_json, ruta_curso, datos)
                except Exception as e:
                    r = {"archivo": nombre, "codigo": "ERROR", "aciertos": 0,
                         "total": datos.total_preguntas, "error": str(e)}
                nuevos.append(r)
                Clock.schedule_once(lambda dt, k=i + 1, e=estado_de(r): pop.avance(k, e))
            Clock.schedule_once(lambda dt: self._fin_calificacion(
                nuevos, datos, pop, cancelar.is_set(), al_terminar))

        threading.Thread(target=trabajo, daemon=True).start()

    def _fin_calificacion(self, nuevos, datos, pop, cancelado, al_terminar):
        """De vuelta en la interfaz: guarda las notas y muestra el resumen."""
        import registro_notas as RN
        if datos.nombre != self.examen:
            self.errores = []
        self.examen = datos.nombre
        self._guardar_registros([r for r in nuevos if r["codigo"] != "ERROR"])
        # Las hojas ilegibles no son notas: se muestran solo en esta sesión
        self.errores = [r for r in nuevos if r["codigo"] == "ERROR"] + self.errores
        self.construir()

        if al_terminar is not None:
            pop.dismiss()
            al_terminar(nuevos)
            return
        repetidos = RN.detectar_conflictos(self._leer_notas())
        cuenta = {"ok": 0, "revisar": 0, "error": 0}
        for r in nuevos:
            cod = str(r["codigo"])
            if cod == "ERROR":
                cuenta["error"] += 1
            elif not cod.isdigit() or cod in repetidos:
                cuenta["revisar"] += 1
            else:
                cuenta["ok"] += 1
        pop.terminar(cuenta, cancelado, al_cerrar=lambda: None)

    def _ruta_notas(self):
        app = App.get_running_app()
        dir_salida = app.ruta_curso / "resultados"
        dir_salida.mkdir(parents=True, exist_ok=True)
        return dir_salida / f"notas_{self.examen}.json"

    def _leer_notas(self):
        notas_path = self._ruta_notas()
        if not notas_path.exists():
            return []
        try:
            return json.loads(notas_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _guardar_registros(self, nuevos):
        """Agrega/actualiza registros en notas_<examen>.json (clave: archivo).
        Las hojas con ERROR no se guardan: no son una nota (se ven en pantalla)."""
        registros = {r.get("archivo", ""): r for r in self._leer_notas()}
        for r in nuevos:
            registros[r["archivo"]] = r
        self._ruta_notas().write_text(
            json.dumps(list(registros.values()), indent=2, ensure_ascii=False),
            encoding="utf-8")

    def _editar_codigo(self, r):
        cont = BoxLayout(orientation="vertical", spacing=dp(8), padding=[dp(8), dp(10)])
        cont.add_widget(_ajustar_texto(Label(
            text="Escribe el código que el estudiante debía marcar (3 números).",
            size_hint_y=None, height=dp(40), font_size="13sp", color=GRIS,
            halign="left", valign="middle")))
        actual = "".join(c for c in r.get("codigo", "") if c.isdigit())
        ti = TextInput(text=actual, multiline=False, input_filter="int",
                       hint_text="Ej.: 007", size_hint_y=None, height=dp(48))
        cont.add_widget(ti)
        lbl = Label(text="", size_hint_y=None, height=dp(22), font_size="13sp",
                    color=(0.776, 0.157, 0.157, 1))
        cont.add_widget(lbl)
        cont.add_widget(Widget())
        btn = Factory.BotonAccion(text="Guardar", size_hint_y=None, height=dp(50))
        cont.add_widget(btn)
        pop = Popup(title="Corregir código", content=cont, size_hint=(0.88, 0.5))

        def _ok(*_):
            nuevo = ti.text.strip()
            if not nuevo.isdigit():
                lbl.text = "Solo números, por favor."
                return
            nuevo = nuevo.zfill(3)
            r["codigo"] = nuevo
            self._actualizar_notas_codigo(r["archivo"], nuevo)
            pop.dismiss()
            self.construir()

        btn.bind(on_release=_ok)
        pop.open()

    def _actualizar_notas_codigo(self, archivo, nuevo):
        data = self._leer_notas()
        for e in data:
            if e.get("archivo") == archivo:
                e["codigo"] = nuevo
                e["codigo_corregido"] = True
        self._ruta_notas().write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                      encoding="utf-8")

    # ── Cámara (solo Android / iOS) ───────────────────────────────────────────
    def _ruta_captura(self):
        """Carpeta donde la cámara guardará la foto. En Android usa la carpeta
        externa de la app (sí es accesible por la app de cámara); en otro caso,
        el directorio de datos del usuario."""
        if platform == "android":
            try:
                from jnius import autoclass  # type: ignore
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                ctx = PythonActivity.mActivity
                ext = ctx.getExternalFilesDir(None)
                if ext is not None:
                    return Path(ext.getAbsolutePath()) / "captura_omr.jpg"
            except Exception:
                pass
        return Path(App.get_running_app().user_data_dir) / "captura_omr.jpg"

    def _tomar_foto(self, *_):
        if platform == "android":
            self._pedir_permiso_camara()
            return
        if platform == "ios":
            try:
                from plyer import camera  # type: ignore
            except Exception:
                aviso("Cámara", "No pudimos usar la cámara de este dispositivo.")
                return
            destino = self._ruta_captura()
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            try:
                camera.take_picture(filename=str(destino), on_complete=self._foto_lista)
            except Exception as e:
                aviso("Cámara", f"No pudimos abrir la cámara: {e}")
            return
        aviso("Cámara", "La cámara solo funciona en el celular. Aquí puedes usar "
              "'Desde la galería' para elegir las fotos.")

    def _pedir_permiso_camara(self):
        """Pide el permiso de cámara (solo la primera vez) y luego la abre."""
        try:
            from android.permissions import (request_permissions, check_permission,  # type: ignore
                                             Permission)
        except Exception:
            self._abrir_camara_c4k()
            return
        if check_permission(Permission.CAMERA):
            self._abrir_camara_c4k()
            return

        def _respuesta(_permisos, concedidos):
            if concedidos and all(concedidos):
                Clock.schedule_once(lambda dt: self._abrir_camara_c4k(), 0.2)
            else:
                Clock.schedule_once(lambda dt: aviso(
                    "Cámara", "Para tomar fotos necesitamos permiso de cámara.\n\n"
                    "Puedes darlo en Ajustes del teléfono > Aplicaciones > "
                    "CalificadorApp > Permisos."), 0)
        request_permissions([Permission.CAMERA], _respuesta)

    def _abrir_camara_c4k(self):
        """Cámara integrada con camera4kivy (CameraX): vista previa en vivo
        dentro de la app + botón de captura."""
        try:
            from camera4kivy import Preview  # type: ignore
        except Exception as e:
            aviso("Cámara", "No pudimos iniciar la cámara: %s\n\n"
                  "Mientras tanto, puedes usar 'Desde la galería'." % e)
            return
        try:
            cont = FloatLayout()
            self._preview = Preview(aspect_ratio="4:3",
                                    size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
            cont.add_widget(self._preview)

            btn_cap = Factory.BotonAccion(text="Tomar foto", size_hint=(None, None),
                                          size=(dp(180), dp(60)),
                                          pos_hint={"center_x": 0.5, "y": 0.03})
            btn_cap.bind(on_release=lambda *_: self._preview.capture_photo(location="private"))
            cont.add_widget(btn_cap)

            btn_x = BotonCerrar(size_hint=(None, None), size=(dp(52), dp(52)),
                                pos_hint={"right": 0.97, "top": 0.97})
            btn_x.color_fondo = (0, 0, 0, 0.45)
            btn_x.color_fondo_down = (0, 0, 0, 0.65)
            cont.add_widget(btn_x)

            self._popup_cam = Popup(title="Encuadra la hoja completa", content=cont,
                                    size_hint=(1, 1), auto_dismiss=False)
            btn_x.bind(on_release=lambda *_: self._popup_cam.dismiss())
            self._popup_cam.bind(
                on_open=lambda *_: self._preview.connect_camera(
                    camera_id="back", filepath_callback=self._foto_c4k,
                    enable_video=False),
                on_pre_dismiss=lambda *_: self._desconectar_c4k())
            self._popup_cam.open()
        except Exception as e:
            import traceback
            aviso("Cámara", "No pudimos iniciar la cámara: %s\n\n%s"
                  % (e, traceback.format_exc()))

    def _desconectar_c4k(self):
        try:
            self._preview.disconnect_camera()
        except Exception:
            pass

    def _foto_c4k(self, path):
        """camera4kivy llama esto cuando la foto quedó guardada (otro hilo)."""
        Clock.schedule_once(lambda dt: self._tras_captura_c4k(path), 0)

    def _tras_captura_c4k(self, path):
        p = Path(str(path)) if path else None
        if p is None or not p.exists():
            return  # puede ser un mensaje de aviso, no una ruta real
        try:
            self._popup_cam.dismiss()
        except Exception:
            pass
        # Espera a que se cierre la cámara antes de abrir la ventana de progreso
        Clock.schedule_once(lambda dt: self._foto_lista(str(p)), 0.3)

    def _foto_lista(self, ruta_foto):
        """La cámara terminó: se califica la foto con la misma ventana de
        progreso que las fotos cargadas, y luego se muestra la hoja marcada."""
        p = Path(str(ruta_foto)) if ruta_foto else None
        if not p or not p.exists():
            aviso("Cámara", "No nos llegó la foto. Inténtalo de nuevo.")
            return
        # Se mueve a la carpeta del curso (no queda en la galería)
        self._iniciar_calificacion([str(p)], mover=True,
                                   al_terminar=self._mostrar_foto_calificada)

    def _mostrar_foto_calificada(self, registros):
        r = registros[0] if registros else None
        if r is None or r["codigo"] == "ERROR":
            aviso("No pudimos calificarla", (r or {}).get("error") or
                  "No logramos leer la hoja. Prueba con más luz y la hoja completa en la foto.")
            return
        self._ver_hoja(r)

    @staticmethod
    def _np_a_textura(img_bgr):
        import cv2
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.flip(rgb, 0)  # el origen de la textura de Kivy está abajo
        h, w = rgb.shape[:2]
        tex = Texture.create(size=(w, h), colorfmt="rgb")
        tex.blit_buffer(rgb.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        return tex


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: REGISTRO DE NOTAS (Paso 5)  ·  Excel cruzando código -> estudiante
# ─────────────────────────────────────────────────────────────────────────────
class RegistroScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)
        self.ultimo_excel = None
        self.mensaje = ""

    def on_pre_enter(self, *_):
        self.ultimo_excel = None
        self.mensaje = ""
        self.construir()

    def construir(self):
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Notas", f"Curso {app.grado}\u00b0{app.curso}"))

        import registro_notas as RN
        examenes = RN.examenes_disponibles(app.ruta_curso)
        if not examenes:
            b.add_widget(_vacio("Todavía no hay notas",
                                "Cuando califiques hojas en 'Calificar', aquí podrás "
                                "armar la planilla de Excel.", alto=150))
            b.add_widget(Widget())
            self._volver(b)
            return

        tarjeta = Tarjeta(size_hint_y=None, padding=[dp(16), dp(14)], spacing=dp(10))
        tarjeta.bind(minimum_height=tarjeta.setter("height"))
        tarjeta.add_widget(_caption("Examen"))
        self.sp_examen = Spinner(text=examenes[0], values=examenes,
                                 size_hint_y=None, height=dp(48))
        tarjeta.add_widget(self.sp_examen)
        btn = Factory.BotonAccion(text="Crear planilla de notas", size_hint_y=None,
                                  height=dp(52))
        btn.bind(on_release=self._generar)
        tarjeta.add_widget(btn)

        if self.ultimo_excel:
            ref, nombre = self.ultimo_excel
            self.lbl_msg = _ajustar_texto(Label(
                text=self.mensaje, markup=True, size_hint_y=None, height=dp(52),
                font_size="13sp", color=GRIS, halign="center", valign="middle"))
            tarjeta.add_widget(self.lbl_msg)
            fila_b = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
            btn_abrir = Factory.BotonSuave(text="Abrir")
            btn_abrir.bind(on_release=lambda *_: self._abrir(ref, nombre))
            fila_b.add_widget(btn_abrir)
            btn_comp = Factory.BotonSuave(text="Compartir" if PF.ES_ANDROID else "Ver carpeta")
            btn_comp.bind(on_release=lambda *_: self._compartir(ref, nombre))
            fila_b.add_widget(btn_comp)
            tarjeta.add_widget(fila_b)
        b.add_widget(tarjeta)

        b.add_widget(Widget(size_hint_y=None, height=dp(4)))
        b.add_widget(_caption("Más opciones"))
        btn_rep = BotonMenu(icono="registro", titulo="Estadísticas del examen",
                            detalle="Promedio, aprobados y las preguntas más difíciles")
        btn_rep.bind(on_release=self._reporte_docente)
        b.add_widget(btn_rep)

        btn_sem = BotonMenu(icono="examenes", titulo="Enviar al coordinador",
                            detalle="Sube las notas del semestre de forma segura")
        btn_sem.bind(on_release=lambda *_: setattr(
            App.get_running_app().sm, "current", "semestrales"))
        b.add_widget(btn_sem)

        b.add_widget(Widget())
        self._volver(b)

    def _volver(self, b):
        b.add_widget(_boton_volver("Volver al curso", "dashboard"))

    def _reporte_docente(self, *_):
        ruta_curso = App.get_running_app().ruta_curso
        examen = self.sp_examen.text

        def trabajo():
            import reportes
            ruta = reportes.generar_reporte_docente(ruta_curso, examen)
            return PF.guardar_en_descargas(ruta, ruta.name) + (ruta.name,)

        def listo(res, err):
            if err:
                aviso("No pudimos crear las estadísticas", str(err))
                return
            texto, ref, nombre = res
            aviso_archivo("Tus estadísticas están listas",
                          "Promedio, aprobados, análisis por pregunta y gráficas.\n\n"
                          f"Las encuentras en:\n{texto}", ref, nombre)
        en_segundo_plano("Calculando estadísticas\u2026", trabajo, listo)

    def _generar(self, *_):
        app = App.get_running_app()
        import registro_notas as RN
        examen = self.sp_examen.text
        try:
            ruta = RN.generar_registro(app.ruta_curso, examen)
        except Exception as e:
            aviso("No pudimos crear la planilla", str(e))
            return
        if ruta is None:
            aviso("Falta la lista del curso",
                  "Para armar la planilla necesitamos los nombres de los estudiantes.\n\n"
                  "Agrégalos en 'Estudiantes' y vuelve a intentarlo.")
            return
        # Copia en Descargas para encontrarlo, abrirlo o compartirlo fuera de la app
        try:
            texto, ref = PF.guardar_en_descargas(ruta, ruta.name)
        except Exception:
            texto, ref = str(ruta), str(ruta)
        self.ultimo_excel = (ref, ruta.name)
        self.mensaje = f"[b][color={VERDE}]¡Planilla lista![/color][/b]  Está en:\n{texto}"
        self.construir()

    def _abrir(self, ref, nombre):
        err = PF.abrir(ref, nombre)
        if err:
            aviso("No pudimos abrirla",
                  f"Búscala en tu carpeta de Descargas ({nombre}).\n\n"
                  "Necesitas una app de hojas de cálculo, como Excel, Google Sheets o WPS.\n\n"
                  f"({err})")

    def _compartir(self, ref, nombre):
        err = PF.compartir(ref, nombre)
        if err:
            aviso("No pudimos compartirlo", err)


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA: SUBIR SEMESTRALES  ·  genera el .json.enc y lo sube al coordinador
# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de áreas (debe coincidir con el del coordinador; acentos/mayúsculas
# no importan allá, pero un área nueva haría que su sincronización aborte).
AREAS = ("Inglés", "Matemáticas", "Español", "Ciencias")


def _ruta_config_subida():
    return Path(App.get_running_app().user_data_dir) / "config_subida.json"


def _leer_area_guardada():
    """Devuelve la última área elegida (o la primera del catálogo)."""
    try:
        d = json.loads(_ruta_config_subida().read_text(encoding="utf-8"))
        a = d.get("area", "")
        return a if a in AREAS else AREAS[0]
    except Exception:
        return AREAS[0]


def _guardar_area(area):
    try:
        _ruta_config_subida().write_text(
            json.dumps({"area": area}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class SemestralesScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cont = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self.add_widget(self.cont)

    def on_pre_enter(self, *_):
        self.construir()

    def construir(self):
        import datetime
        import registro_notas as RN
        app = App.get_running_app()
        self.cont.clear_widgets()
        b = self.cont
        b.add_widget(Encabezado("Enviar al coordinador", f"Curso {app.grado}\u00b0{app.curso}"))

        examenes = RN.examenes_disponibles(app.ruta_curso)
        if not examenes:
            b.add_widget(_vacio("Todavía no hay notas para enviar",
                                "Primero califica las hojas en 'Calificar'.", alto=140))
            b.add_widget(Widget())
            self._volver(b)
            return

        aviso_lbl = _ajustar_texto(Label(
            text="Enviamos las notas del semestre protegidas, para que solo "
                 "coordinación pueda abrirlas.",
            size_hint_y=None, height=dp(44), font_size="13.5sp", color=GRIS,
            halign="left", valign="middle"))
        b.add_widget(aviso_lbl)

        tarjeta = Tarjeta(size_hint_y=None, padding=[dp(16), dp(14)], spacing=dp(6))
        tarjeta.bind(minimum_height=tarjeta.setter("height"))
        tarjeta.add_widget(_caption("Examen"))
        self.sp_examen = Spinner(text=examenes[0], values=examenes,
                                 size_hint_y=None, height=dp(48))
        tarjeta.add_widget(self.sp_examen)

        # Período semestral (formato AAAA-S)
        hoy = datetime.date.today()
        anios = [str(a) for a in range(hoy.year - 1, hoy.year + 2)]
        fila_per = BoxLayout(size_hint_y=None, height=dp(74), spacing=dp(10))
        col_a = BoxLayout(orientation="vertical", spacing=dp(4))
        col_a.add_widget(_caption("Año"))
        self.sp_anio = Spinner(text=str(hoy.year), values=anios,
                               size_hint_y=None, height=dp(48))
        col_a.add_widget(self.sp_anio)
        col_s = BoxLayout(orientation="vertical", spacing=dp(4))
        col_s.add_widget(_caption("Semestre"))
        self.sp_semestre = Spinner(text=("1" if hoy.month <= 6 else "2"),
                                   values=("1", "2"), size_hint_y=None, height=dp(48))
        col_s.add_widget(self.sp_semestre)
        fila_per.add_widget(col_a)
        fila_per.add_widget(col_s)
        tarjeta.add_widget(fila_per)

        # Área (se recuerda la última elegida)
        tarjeta.add_widget(_caption("Área"))
        self.sp_area = Spinner(text=_leer_area_guardada(), values=AREAS,
                               size_hint_y=None, height=dp(48))
        tarjeta.add_widget(self.sp_area)
        b.add_widget(tarjeta)

        b.add_widget(Widget())
        btn_coord = Factory.BotonAccion(text="Enviar notas",
                                        size_hint_y=None, height=dp(54))
        btn_coord.bind(on_release=self._enviar_coordinador)
        b.add_widget(btn_coord)
        self._volver(b)

    def _enviar_coordinador(self, *_):
        app = App.get_running_app()
        examen = self.sp_examen.text
        periodo = f"{self.sp_anio.text}-{self.sp_semestre.text}"
        area = self.sp_area.text
        ruta_curso = app.ruta_curso

        def _hacer():
            _guardar_area(area)

            def trabajo():
                import reportes
                import subida
                # 1) Generar el .json.enc cifrado  2) subirlo
                ruta = reportes.generar_json_salon(ruta_curso, examen, periodo)
                ok, msg = subida.subir_a_drive(str(ruta), area, periodo)
                return ruta, ok, msg

            def listo(res, err):
                if err:
                    aviso("No pudimos preparar el envío", str(err))
                    return
                ruta, ok, msg = res
                if ok:
                    aviso("¡Notas enviadas!", "Coordinación ya tiene tus notas.\n\n"
                          f"{ruta.name}")
                else:
                    aviso("No pudimos enviarlas",
                          f"Preparamos el archivo, pero no se pudo subir:\n{msg}\n\n"
                          "Revisa tu conexión a internet e inténtalo de nuevo.\n\n"
                          f"Archivo: {ruta.name}")
            en_segundo_plano("Enviando tus notas\u2026", trabajo, listo)

        confirmar("¿Enviamos estas notas?",
                  f"'{examen}'  ·  curso {app.grado}\u00b0{app.curso}\n"
                  f"Área: {area}  ·  Semestre {periodo}",
                  "Sí, enviar", _hacer, peligro=False)

    def _volver(self, b):
        b.add_widget(_boton_volver("Volver a notas", "registro"))


# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────
class CalificadorApp(App):
    profesor = ""
    grado = ""
    curso = ""
    ruta_curso = None

    def build(self):
        self.title = "Calificador · Liceo Sahagún"
        # En Android la carpeta de instalación es de solo lectura: movemos el
        # "directorio de trabajo" a la carpeta privada de la app (sí escribible),
        # para que 'profesores/' y todos los datos se guarden sin problemas.
        # En PC, los datos van siempre junto a la app (antes dependían de la
        # carpeta desde donde se abría, y parecía que se "perdían").
        try:
            os.chdir(self.user_data_dir if platform == "android" else _DIR)
        except Exception:
            pass
        _registrar_fuentes()
        Window.clearcolor = FONDO
        # Al escribir, la pantalla sube para que el campo quede sobre el teclado
        Window.softinput_mode = "below_target"
        if platform != "android":
            Window.size = (400, 720)   # vista tipo celular para probar en PC
        GS.inicializar_sistema()
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.sm.add_widget(SetupScreen(name="setup"))
        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(DashboardScreen(name="dashboard"))
        self.sm.add_widget(EstudiantesScreen(name="estudiantes"))
        self.sm.add_widget(ExamenesScreen(name="examenes"))
        self.sm.add_widget(ClavesScreen(name="claves"))
        self.sm.add_widget(CalificarScreen(name="calificar"))
        self.sm.add_widget(RegistroScreen(name="registro"))
        self.sm.add_widget(SemestralesScreen(name="semestrales"))
        self.sm.current = "home" if _subdirs(BASE) else "setup"
        Window.bind(on_keyboard=self._tecla)
        return self.sm

    # Pantalla a la que lleva "Atrás" desde cada una
    _ATRAS = {"estudiantes": "dashboard", "examenes": "dashboard",
              "calificar": "dashboard", "registro": "dashboard", "dashboard": "home",
              "claves": "examenes", "semestrales": "registro"}

    def _tecla(self, _window, tecla, *_):
        """Botón "Atrás" de Android (y Esc en PC): vuelve a la pantalla anterior
        en lugar de cerrar la app. En el inicio pregunta antes de cerrarla."""
        if tecla != 27:
            return False
        if any(isinstance(w, ModalView) for w in Window.children):
            return True   # hay una ventana abierta (p. ej. calificando): no salir
        destino = self._ATRAS.get(self.sm.current)
        if destino:
            self.sm.current = destino
        else:
            pedir_salir()   # en el inicio: preguntar antes de cerrar
        return True

    def on_start(self):
        _solicitar_permisos_android()

    def ir_a_home(self):
        self.sm.current = "home"


if __name__ == "__main__":
    CalificadorApp().run()