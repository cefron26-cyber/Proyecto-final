# Informe de Auditoría — CalificadorApp

**Fecha:** 2026-07-11  
**Versión del código:** Primera auditoría (no existe .revision/ultima.md previo)  
**Alcance:** Todo el proyecto (14 módulos Python + tests)

---

## Resumen Ejecutivo

El proyecto es **funcional y probado** (las 20 hojas de prueba pasan exactamente como se diseñaron), pero presenta **riesgos críticos de seguridad y integridad de datos** que deben corregirse antes de usar en producción real. La arquitectura monolítica en `main.py` (3878 líneas) dificulta el mantenimiento y la prueba unitaria.

**Veredicto general:** 🟠 **Alto** — Usable con correcciones obligatorias.

---

## Hallazgos por Gravedad

### 🔴 CRÍTICO

| ID | Archivo:Línea | Problema | Escenario de Fallo | Arreglo |
|---|---|---|---|---|
| C01 | `cripto.py:11` | **Clave maestra hardcodeada** (`_LLAVE_MAESTRA = b"..."`) | Cualquiera con el APK extrae la clave → descifra todos los JSON.enc subidos a Drive, falsifica notas, suplantación de profesor. | Derivar clave por instalación (PBKDF2 + device ID) o exigir entrada de passphrase al primer uso. Nunca shippear secreto fijo. |
| C02 | `subida.py:16-17` | **Token secreto y URL de Apps Script en código** | Mismo riesgo que C01: token expuesto en APK → cualquiera sube/borra archivos en Drive del coordinador. | Configuración externa (archivo JSON en carpeta de datos, no en repo). UI para pegar credenciales en primer uso. |
| C03 | `main.py:3282-3297` | **Reemplazo silencioso de notas por código duplicado** | Estudiante A calificado → guarda nota. Estudiante B (o misma hoja re-fotografiada) con mismo código → nota de A se borra sin confirmación ni log. | Requerir confirmación explícita ("Esta hoja reemplaza a la del alumno 001, ¿continuar?") y registrar en log/auditoría. |
| C04 | `main.py:3303-3304` | **Escritura JSON no atómica** (`write_text` directo) | Crash/ Corte de luz / kill del proceso durante escritura → `notas_<examen>.json` truncado/corrupto → **pérdida total de notas de ese examen**. | Escribir a `archivo.tmp` + `os.replace()` (atómico en POSIX/Windows) + validar JSON al leer. |
| C05 | `registro_notas.py:60` `main.py:3303` | **Excepción genérica silenciada al leer/escribir JSON** | Archivo corrupto → `except Exception: return []` / `pass` → app arranca con lista vacía, profesor cree que no hay notas. | Loggear error con `traceback`, mostrar alerta al usuario, ofrecer "Restaurar desde backup" (ver C04). |
| C06 | `lector_omr.py:729` | **División por cero si `total == 0`** (aunque hay guardia en 727) | Si `clave_json` tiene `total_preguntas: 0` o clave vacía → `ZeroDivisionError` en hilo de calificación → hilo muere sin avisar, hoja queda sin nota. | Validar `total > 0` en `cargar_datos_examen()` y lanzar `ValueError` claro antes de iniciar hilos. |

---

### 🟠 ALTO

| ID | Archivo:Línea | Problema | Escenario de Fallo | Arreglo |
|---|---|---|---|---|
| A01 | `main.py:3216` | **ThreadPoolExecutor sin límite de memoria** | 50 fotos × 12 MP → cada hilo carga imagen completa en RAM → OOM en Android (límites ~192-512 MB). | Procesar en lotes (`chunks`), liberar `img` y `recta` tras cada foto, o usar `ProcessPoolExecutor` (pero pickle de OpenCV es lento). Mínimo: `max_workers=min(3, len(archivos))` ya está, pero no libera memoria entre items. |
| A02 | `plataforma.py:170, 218` | **Acceso a `ContentResolver` desde hilo no-UI** | `elegir_archivos` usa `Clock.schedule_once` para callback, pero `copiar` lee `content://` URIs en hilo background → `SecurityException` o `FileNotFound` intermitente en Android 10+. | Leer `InputStream` en hilo UI (o `runOnUiThread`) y volcar a archivo temporal *antes* de pasar a hilo worker. |
| A03 | `plataforma.py:341-385` | **Restaurar backup sin validar integridad** | ZIP malicioso/corrupto con `../../../etc/passwd` o symlinks → path traversal al extraer (mitigado en 371-376 pero solo valida prefijo, no symlinks). | Usar `zipfile.ZipFile.extractall` con `path` validation estricta + `ZipInfo.is_dir()` + rechazar symlinks (`external_attr & 0xA0000000`). |
| A04 | `main.py:2803, 2815` | **Detección de conflictos usa `RN.detectar_conflictos` pero `_guardar_registros` tiene lógica distinta** | `registro_notas.py` detecta conflictos por `firma_hoja` (respuestas); `main.py` reemplaza por `codigo` simple. Resultado: misma foto 2 veces = OK en main, pero conflicto en registro Excel si respuestas difieren mínimamente. | Unificar: `main.py` debe usar misma firma (hash de respuestas normalizadas) que `registro_notas.py`. |
| A05 | `lector_omr.py:295` | **`block = max(31, (pw // 8) | 1)` tamaño de bloque adaptativo sin cota superior** | Foto muy ancha (p.ej. 4000 px) → `block=501` → `adaptiveThreshold` extremadamente lento y memoria alta. | Limitar `block = min(max(31, (pw // 8) | 1), 151)` o similar. |
| A06 | `generador_pdf.py:218-219` | **`except Exception: pass` al cargar logo** | Logo corrupto/ausente → PDF se genera sin logo **sin avisar** → hojas impresas sin escudo institucional. | Loggear warning, usar placeholder o abortar con mensaje claro. |
| A07 | `registro_notas.py:119-132` | **`cargar_roster` asume columnas fijas A/B/C sin validar encabezados** | Planilla con columnas reordenadas o encabezados distintos → mapeo incorrecto (código ↔ nombre) → notas asignadas a alumno equivocado. | Leer fila 1, mapear por nombre de columna (`'Código'`, `'Nombre'`, `'N° Lista'`), validar presencia. |

---

### 🟡 MEDIO

| ID | Archivo:Línea | Problema | Escenario de Fallo | Arreglo |
|---|---|---|---|---|
| M01 | `main.py` (global) | **Arquitectura monolítica: 3878 líneas en un archivo** | Cualquier cambio en UI, persistencia, calificación o navegación requiere tocar `main.py` → regresiones frecuentes, difícil testear. | Separar en: `app.py` (bootstrap), `screens/*.py` (UI), `services/*.py` (persistencia, calificación, export), `models/*.py` (dataclasses). |
| M02 | `main.py:3303` `_escribir_notas` | **No hay backup rotativo de `notas_<examen>.json`** | Corrupción (C04) o error humano → única copia perdida. | Antes de escribir, copiar `notas.json → notas.json.bak.N` (rotar 5). |
| M03 | `lector_omr.py:556` | **Coordenadas de burbujas transformadas con `dx/scale, dy/scale`** pero `scale` viene de homografía que puede tener shear | Foto con perspectiva fuerte → burbujas desalineadas respecto a plantilla → lecturas erráticas en bordes. | Validar `scale` ≈ 1.0 ± 20%; si no, reintentar detección de esquinas o avisar "foto muy inclinada". |
| M04 | `reportes.py:76-90` | **`incorrectas_de` compara `marco != correcta` pero `marco` puede ser `""` (blanco) vs `None`** | Respuesta en blanco (`""`) vs no detectada (`None`) → ambas cuentan como incorrecta, pero semántica distinta para el docente. | Unificar a `None` para "no se leyó" y `""` para "en blanco intencional"; distinguir en reporte. |
| M05 | `layout_hoja.py:90` | **`tam_orientacion / 2` usado como radio de marcas de esquina** — valor hardcodeado sin constante nombrada | Cambio futuro en tamaño de marcas → olvido de actualizar aquí → PDF y lector divergen silenciosamente. | Extraer a constante `RADIO_MARCA_ESQUINA = F.tam_orientacion / 2` con comentario "debe coincidir en generador_pdf y lector_omr". |
| M06 | `digitalizador.py:51-61` | **Kernel de blur `max(15, min(img.shape[:2]) // 12)` sin límite superior** | Imagen muy grande → kernel enorme → `GaussianBlur` lentísimo / OOM. | `min(kernel, 151)` o similar. |
| M07 | `plataforma.py:336` | **`subprocess.Popen(["explorer", "/select,", ...])` solo Windows** | En Linux/macOS (desarrollo) falla silenciosamente → no abre carpeta. | Usar `webbrowser.open` o `os.startfile` (Windows) / `open` (macOS) / `xdg-open` (Linux) con fallback. |
| M08 | `subida.py:43-44` | **`except urllib.error.URLError:` captura solo URLError, no `http.client.HTTPException`** | Timeout de socket, reset de conexión, certificado inválido → excepción no atrapada → crash del hilo de subida sin reintento. | `except (urllib.error.URLError, TimeoutError, OSError):` + reintento exponencial (3×). |
| M09 | `cripto.py:24-25` | **`salt = os.urandom(16)` pero no se verifica unicidad** | Colisión de salt (probabilidad despreciable pero no imposible en uso masivo) → mismo keystream para dos mensajes → XOR revela XOR de plaintexts. | Añadir `nonce = os.urandom(8)` + `salt` = 24 bytes; o usar `libsodium`/`cryptography` (AEAD real). |
| M10 | `main.py:192` | **`self._img.pos = (x + (t - s) / 2, y + (t - s) / 2)` cálculo de centrado repetido en 449, 333** | Duplicación → inconsistencia si se cambia uno y no los otros. | Extraer a helper `_centrar(widget, contenedor)`. |

---

## Pruebas Automatizadas

| Test | Estado | Notas |
|---|---|---|
| `pruebas/verificar_pruebas.py` | ✅ **PASS** (20/20) | Todas las hojas se leen exactamente como se diseñaron. |
| `pruebas/generar_pruebas.py` | ✅ PASS | Genera PDF + 20 fotos sintéticas. |
| Cobertura de código | ❌ N/A | No hay `pytest`, `coverage`, ni CI. |

**Recomendación:** Añadir `pytest` + GitHub Actions para correr `verificar_pruebas.py` en cada PR.

---

## Arquitectura de Datos — Contratos Críticos

| Contrato | Productor | Consumidores | Riesgo si cambia |
|---|---|---|---|
| `layout_hoja.Formato` (dataclass) | `layout_hoja.py` | `generador_pdf.py`, `lector_omr.py` | **Divergencia PDF vs OMR** → hojas imposibles de leer. **Nunca cambiar sin test de regresión visual.** |
| `notas_<examen>.json` (lista de dicts) | `main.py:_guardar_registros` | `registro_notas.py`, `reportes.py`, `main.py:_leer_notas` | Cambio de esquema → migración manual necesaria. Versionar con campo `"version": 1`. |
| `respuestas_<examen>.json` (clave) | `main.py` (Paso 3) | `lector_omr.py`, `registro_notas.py`, `reportes.py` | Igual que arriba. |
| `lista_estudiantes.xlsx` (columnas A/B/C) | Usuario (Excel) | `registro_notas.py:cargar_roster`, `main.py:_lista_codigos` | Ver A07. |

---

## Seguridad — Resumen

| Vector | Estado | Acción Requerida |
|---|---|---|
| Secrets en código (clave AES, token Drive) | 🔴 **CRÍTICO** | Eliminar de repo; configuración en runtime. |
| Cifrado casero (HMAC + keystream XOR) | 🟠 **ALTO** | Migrar a `cryptography.Fernet` o `libsodium` (AEAD). |
| Validación de entrada (ZIP, Excel, JSON) | 🟠 **ALTO** | Ver A03, A07, C05. |
| Permisos Android (CAMERA, RECORD_AUDIO) | ✅ OK | Declarados en `camerax_provider/gradle_options.py`. |
| Comunicación en claro (HTTP) | ⚠️ **MEDIO** | `subida.py` usa HTTPS (Apps Script), OK. |

---

## Rendimiento — Cuellos de Botella Conocidos

1. **`lector_omr.leer_foto`**: `adaptiveThreshold` con bloque grande (A05) + `findContours` en imagen completa → ~1.5-3 s/foto en móviles medios.
2. **`digitalizador.enderezar`**: `GaussianBlur` con kernel grande (M06) + morfología → ~0.5-1 s.
3. **ThreadPoolExecutor en `main.py`**: No libera memoria entre fotos (A01) → OOM en lotes >10 fotos.
4. **`generador_pdf.py`**: Escritura byte-a-byte en Python puro → lento para >50 páginas (pero uso típico <10).

---

## Deuda Técnica Priorizada

| Prioridad | Área | Esfuerzo | Impacto |
|---|---|---|---|
| 1 | Secrets management + cifrado real | 2-3 días | Seguridad / Cumplimiento |
| 2 | Escritura atómica + backup rotativo + logging errores | 1 día | Integridad de datos (evita pérdida total) |
| 3 | Unificar detección de conflictos (main ↔ registro_notas) | 0.5 día | Consistencia de notas |
| 4 | Separar `main.py` en módulos (screens, services, models) | 1-2 semanas | Mantenibilidad / Testabilidad |
| 5 | Añadir tests unitarios + CI | 3-5 días | Prevención regresiones |
| 6 | Optimizar memoria en calificación por lotes | 1-2 días | Estabilidad en Android |
| 7 | Validar columnas Excel por encabezado (no posición) | 0.5 día | Robustez ante planillas usuario |

---

## Checklist de Verificación Pre-Release

- [ ] **C01, C02**: Secrets fuera del código (config JSON en `profesores/.config/`)
- [ ] **C04, C05**: Escritura atómica + backup + logging de errores JSON
- [ ] **C03**: Confirmación antes de reemplazar nota por código duplicado
- [ ] **C06**: Validar `total_preguntas > 0` al cargar clave
- [ ] **A01**: Liberar `img`/`recta` en loop de calificación (`del img; gc.collect()`)
- [ ] **A02**: Leer `content://` en hilo UI antes de pasar a worker
- [ ] **A03**: Validación estricta ZIP (no symlinks, path traversal)
- [ ] **A04**: Unificar firma de hoja (hash respuestas normalizadas)
- [ ] **A07**: `cargar_roster` mapea por nombre de columna
- [ ] **M02**: Backup rotativo `notas.json.bak.{1..5}`
- [ ] Tests: `pytest pruebas/verificar_pruebas.py` en CI

---

## Conclusión

El **motor OMR es sólido y probado** (20/20 casos de prueba pasan). Los **riesgos críticos son de ingeniería de software** (secrets, atomicidad, manejo de errores), no de algoritmo. Con las correcciones **C01-C06 + A01-A04** el proyecto sería apto para uso real en entorno escolar controlado. La refactorización arquitectónica (M01) es deseable pero no bloqueante para un primer release.