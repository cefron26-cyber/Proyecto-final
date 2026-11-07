# Plan de Refactorización por Fases — Separación de `main.py`

> ## Estado al 2026-11-07 — qué se hizo y qué se descartó
>
> Criterio: solo se ejecutó lo que se puede **verificar sin el teléfono**
> (Kivy no corre en la PC de desarrollo) y cuyo beneficio supera su riesgo.
>
> **Hecho**
> - Proyecto bajo git (`.gitignore` excluye datos de docentes y credenciales).
> - `notas.py`: reglas de las notas (estado de cada hoja, orden, reemplazos,
>   historial) fuera de `CalificarScreen`, sin Kivy. Las hojas siguen siendo
>   dicts (no se pierde ningún campo). `main.py` solo delega.
> - `almacen_json.py` y `credenciales.py` (de las correcciones 🔴).
> - Pruebas con pytest en `pruebas/test_*.py` (48) + GitHub Actions
>   (`.github/workflows/pruebas.yml`). Correr: `python -m pytest pruebas -q`.
>
> **Descartado (riesgo mayor que el beneficio)**
> - Carpeta `src/` + `pyproject.toml`: buildozer espera `main.py` en la raíz.
> - Dataclasses para las notas (Fase 2): reconstruir las hojas con campos
>   fijos borraría campos como `imagen`, `codigo_corregido`, `foto_borrada`.
> - Mover widgets, tema KV y pantallas (Fases 1, 4 y 5): el tema KV debe
>   cargarse antes que cualquier pantalla y nada de eso se puede probar sin
>   el teléfono. Solo se haría pantalla por pantalla, compilando el APK y
>   probándolo en el celular después de cada una.
> - Quitar `App.get_running_app()` (38 usos) y el `navigation.py` con
>   historial: son cambios de lógica, no de estructura.
> - Mantener las importaciones diferidas de OpenCV/numpy/openpyxl: subirlas
>   al inicio de un módulo alargaría el arranque en Android.
>
> El resto de este documento es el plan original, como referencia.

**Objetivo:** Dividir `main.py` (3878 líneas) en módulos cohesivos sin romper funcionalidad.
**Estrategia:** Extracción incremental con tests de regresión en cada fase. El archivo original queda como `main_legacy.py` hasta validar todo.

---

## Análisis de Dependencias Actuales

```
main.py (3878 líneas)
├── UI / Widgets (líneas 153-780)
│   ├── Tarjeta, InsigniaEscudo, BotonMenu, BotonHerramienta, Pildora
│   ├── BotonCerrar, BotonIcono, Casilla, _Pulso, CirculoProgreso
│   ├── _VentanaSinRastro, PopupEspera, PopupProgreso
│   └── Encabezado, Portada
├── Utilidades UI (83-114, 119-150, 199-235, 600-670)
├── Navegación / Pantallas (1487-3812)
│   ├── SetupScreen, HomeScreen, DashboardScreen
│   ├── EstudiantesScreen, ExamenesScreen, ClavesScreen
│   ├── CalificarScreen, GaleriaHojas, RegistroScreen, SemestralesScreen
├── Lógica de negocio / Servicios (1063-1450)
│   ├── _subdirs, aviso, confirmar, en_segundo_plano
│   ├── codigo_de, nota_local, leer/guardar_lista_estudiantes
│   ├── importar_planilla, generar_plantilla_estudiantes
│   ├── listar_examenes, guardar_clave, generar_pdf_a_descargas
│   ├── _fotos_de_hoja, examenes_con_fotos, borrar_fotos_examenes
│   ├── generar_codigos_a_descargas
├── Configuración subida (3675-3695)
└── App bootstrap (3813-3878)
```

---

## Fases Propuestas

### Fase 0 — Preparación (0.5 días)
**Objetivo:** Base segura para refactorizar.

| Tarea | Detalle |
|---|---|
| 0.1 | `git tag pre-refactor` + rama `refactor/main-split` |
| 0.2 | Copiar `main.py → main_legacy.py` (referencia) |
| 0.3 | Añadir `pytest` + `verificar_pruebas.py` como test de regresión automático |
| 0.4 | Crear `pyproject.toml` con `src/calificador` como paquete |
| 0.5 | Verificar que `python -m calificador` arranca igual |

**Criterio de salida:** `pytest pruebas/verificar_pruebas.py` pasa; app arranca desde `main_legacy.py`.

---

### Fase 1 — Utilidades y Constantes (1 día)
**Archivos nuevos:** `src/calificador/ui/{utils,theme,widgets}.py`

| Extraer a | Contenido | Líneas aprox |
|---|---|---|
| `theme.py` | Colores (AZUL, DORADO, FONDO...), `_registrar_fuentes`, `_textura_del_escudo` | 80 |
| `widgets/base.py` | `Tarjeta`, `InsigniaEscudo`, `_fondo_tarjeta`, `_ajustar_texto`, `_redibujar_al_cambiar` | 120 |
| `widgets/buttons.py` | `BotonMenu`, `BotonHerramienta`, `BotonCerrar`, `BotonIcono`, `Casilla`, `OpcionLetra` | 180 |
| `widgets/feedback.py` | `_Pulso`, `_preparar_pulso`, `_do_press_con_pulso`, `_do_release_con_pulso`, `CirculoProgreso` | 100 |
| `widgets/popups.py` | `_VentanaSinRastro`, `PopupEspera`, `PopupProgreso`, `_tarjeta_blanca`, `_caption`, `_popup_texto`, `aviso`, `confirmar`, `aviso_archivo` | 150 |
| `utils/fs.py` | `_subdirs`, `_tamano` | 20 |
| `utils/threading.py` | `en_segundo_plano` | 30 |

**Migración:** En `main_legacy.py` → `from calificador.ui.widgets import ...` etc.  
**Test:** App arranca, navega entre pantallas, popups funcionan.

---

### Fase 2 — Modelos de Datos (0.5 días)
**Archivo nuevo:** `src/calificador/models/__init__.py`

| Clase / Dataclass | Origen | Responsabilidad |
|---|---|---|
| `FormatoHoja` | `layout_hoja.py` (ya existe) | Geometría — **no tocar** |
| `ExamenClave` | `main.py:1332` `guardar_clave` | nombre, cantidad, clave_letras, formato |
| `Estudiante` | `main.py:1162` `leer_lista_estudiantes` | codigo, nombre, n_lista |
| `NotaHoja` | `main.py:3288` dict en `notas_json` | archivo, codigo, aciertos, total, nota, imagen, firma_hoja, ... |
| `CursoConfig` | `main.py:1063` `_subdirs` + rutas | profesor, grado, curso, ruta_base |
| `SubidaConfig` | `main.py:3675` `_ruta_config_subida` | url_script, token, area |

**Migración:** `main_legacy.py` importa y usa dataclasses; dicts internos se convierten al límite de persistencia.

---

### Fase 3 — Servicios de Persistencia (1.5 días)
**Archivos nuevos:** `src/calificador/services/{storage,excel,pdf,omr,upload}.py`

| Servicio | Funciones principales | Origen en main.py |
|---|---|---|
| `storage.py` | `leer_notas`, `escribir_notas_atomico`, `backup_rotativo`, `leer_clave`, `guardar_clave`, `listar_examenes` | 3269-3304, 1316-1342 |
| `excel.py` | `leer_lista_estudiantes`, `guardar_lista_estudiantes`, `importar_planilla`, `generar_plantilla`, `generar_registro_excel` (de `registro_notas.py`) | 1162-1210, 1261-1270 |
| `pdf.py` | `generar_pdf_a_descargas`, `generar_codigos_a_descargas` | 1343-1360, 1452-1490 |
| `omr.py` | `calificar_foto`, `calificar_lote` (wrapper ThreadPool), `leer_foto` (de `lector_omr.py`) | 3172-3223, `lector_omr.py` |
| `upload.py` | `subir_notas`, `leer_config_subida`, `guardar_config_subida` | 3675-3695, `subida.py` |

**Puntos críticos:**
- `escribir_notas_atomico`: `tmp → os.replace` + rotar 5 backups `.bak.1..5`
- `calificar_lote`: libera `img`/`recta` cada iteración (`del img; gc.collect()`)
- `importar_planilla`: mapear por **encabezado**, no por columna fija (fix A07)

**Test:** `pytest pruebas/verificar_pruebas.py` + test unitario de `storage.escribir_notas_atomico` (simular crash).

---

### Fase 4 — Pantallas (Screens) — La parte grande (3-4 días)
**Estructura:** `src/calificador/screens/{setup,home,dashboard,estudiantes,examenes,claves,calificar,registro,semestrales}.py`

**Patrón común por pantalla:**
```python
# screens/estudiantes.py
from kivy.uix.screenmanager import Screen
from calificador.ui.widgets import Tarjeta, BotonMenu, ...
from calificador.services.storage import leer_lista_estudiantes, guardar_lista_estudiantes
from calificador.models import Estudiante

class EstudiantesScreen(Screen):
    def on_enter(self): ...
    def _construir_lista(self): ...
    # handlers locales
```

| Pantalla | Líneas en main.py | Complejidad | Dependencias |
|---|---|---|---|
| `SetupScreen` | 1487-1568 | Baja | `gestor_salones`, `storage` |
| `HomeScreen` | 1569-1987 | Media | `storage`, `excel`, `pdf` |
| `DashboardScreen` | 1988-2033 | Baja | `storage`, `omr` |
| `EstudiantesScreen` | 2034-2225 | **Alta** | `excel`, `storage`, `models.Estudiante` |
| `ExamenesScreen` | 2226-2383 | Media | `storage`, `pdf` |
| `ClavesScreen` | 2417-2663 | **Alta** | `storage`, `models.ExamenClave` |
| `CalificarScreen` | 2961-3535 | **Muy alta** | `omr`, `storage`, `widgets.GaleriaHojas` |
| `RegistroScreen` | 3536-3674 | Media | `excel` (registro_notas), `reportes` |
| `SemestralesScreen` | 3697-3812 | Media | `storage`, `excel`, `reportes` |
| `GaleriaHojas` | 2664-2960 | **Alta** | `widgets`, `storage`, `omr` |

**Estrategia de extracción:**
1. Una pantalla por commit
2. Mover métodos privados `_metodo` → métodos de la clase
3. Callbacks `lambda` → métodos nombrados (mejor debug)
4. `App.get_running_app()` → inyectar dependencias en `__init__` o `on_enter`

**Test por pantalla:** Navegar a ella, hacer flujo principal, volver.

---

### Fase 5 — App Bootstrap y Navegación (0.5 días)
**Archivos nuevos:** `src/calificador/{app,navigation}.py`

| Componente | Responsabilidad |
|---|---|
| `app.py` | `CalificadorApp` → `build()`, `on_start()`, `on_stop()`, registro de fuentes, tema global |
| `navigation.py` | `ScreenManager` personalizado, transiciones, `ir_a(pantalla, **kwargs)`, stack de navegación |
| `main.py` (nuevo, ~30 líneas) | `from calificador.app import main; main()` |

**Test:** App completa funcional desde `python -m calificador`.

---

### Fase 6 — Limpieza y Validación Final (1 día)

| Tarea | Detalle |
|---|---|
| 6.1 | Borrar `main_legacy.py` |
| 6.2 | `ruff` / `black` en todo el paquete |
| 6.3 | `pytest` suite completa (OMR + unitarios nuevos) |
| 6.4 | Build Android (`buildozer -v android debug`) → probar en dispositivo |
| 6.5 | Documentar arquitectura en `ARCHITECTURE.md` |

---

## Cronograma Estimado

| Fase | Días | Acumulado | Entregable |
|---|---|---|---|
| 0 | 0.5 | 0.5 | Base testable |
| 1 | 1.0 | 1.5 | UI desacoplada |
| 2 | 0.5 | 2.0 | Modelos tipados |
| 3 | 1.5 | 3.5 | Servicios puros (testables) |
| 4 | 3.5 | 7.0 | Pantallas independientes |
| 5 | 0.5 | 7.5 | App limpio |
| 6 | 1.0 | 8.5 | Release candidate |

**Total: ~9 días laborables** (2 semanas calendario con buffer).

---

## Reglas de Oro Durante la Refactorización

1. **Un commit por extracción** — `git diff` debe mostrar solo movimiento + imports.
2. **Tests verdes antes de siguiente extracción** — `pytest` en cada commit.
3. **Sin cambios de lógica** — solo estructura. Bugs se arreglan en issues aparte.
4. **Inyección de dependencias** — nada de `App.get_running_app()` en servicios/pantallas.
5. **Tipado gradual** — `from __future__ import annotations` + type hints en firmas públicas.

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| `GaleriaHojas` y `CalificarScreen` muy acoplados | Alta | Retraso Fase 4 | Extraer `GaleriaHojas` primero como widget reutilizable |
| `ThreadPoolExecutor` + Kivy Clock en `CalificarScreen` | Media | Crash hilos | Mover lógica a `omr.py:calificar_lote` (servicio puro) |
| `registro_notas.py` y `reportes.py` usan dicts crudos | Media | Rotura silenciosa | Fase 2 define `NotaHoja`; adaptadores en servicios |
| Buildozer rompe por imports nuevos | Baja | Build falla | Probar `buildozer android debug` en Fase 3 y 6 |

---

## Métricas de Éxito

- [ ] `main.py` < 100 líneas (solo bootstrap)
- [ ] `src/calificador/` < 500 líneas por archivo
- [ ] Cobertura `pytest` > 60% (servicios + modelos)
- [ ] Build Android exitoso
- [ ] 0 regresiones en `verificar_pruebas.py`
- [ ] Tiempo de arranque app < 2s (igual o mejor)

---

## Próximo Paso Inmediato

¿Quieres que inicie la **Fase 0** (crear rama, `pytest`, `pyproject.toml`, copiar `main_legacy.py`) y te muestre el diff resultante?