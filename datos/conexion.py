"""Estado de conexión de cada cama, DERIVADO de dos fuentes (ADR-024 del backend).

- `estado` de la cama (monitoreo/estado/{cama_id}): online/offline que publica
  el OCR de la Jetson.
- `enlace` del edge (monitoreo/edge/{device_id}/bridge): 1/0 del bridge que
  lleva los datos de la Jetson al server. Desde ADR-024 el OCR publica a un
  broker LOCAL en la Jetson: si se cae el internet o la Jetson entera, el
  `estado` retenido en el server se queda en "online" para siempre — la
  única señal honesta de "ya no llegan datos de esa Jetson" es el enlace.

Reglas (validadas por Cowork para F1.1):
- El estado MOSTRADO se DERIVA, no gana el último evento: "sin_conexion" si el
  enlace del edge de la cama es 0; si no, el estado de la cama (online /
  offline), o None si aún no se conoce. Un enlace 1 NO fuerza "online".
  Enlace desconocido (sin retained, payload raro) = no se marca nada.
- Independiente del orden de llegada: el enlace se guarda por device_id aunque
  todavía no exista ninguna tarjeta de ese edge, y se aplica cuando nace.
- La relación cama -> device_id es el ÚLTIMO visto (no un conjunto que solo
  crece): si una cama cambia de Jetson, deja de colgar del edge viejo.
- device_id es opcional: vitales sin él no tocan el mapeo (y se muestran igual).

Frescura de las vitales (hallazgo de la revisión de F1.1): al volver el enlace
el bridge RE-PUBLICA las vitales retenidas del edge, y le llegan a la app como
mensajes en vivo (retain=0). Si el OCR estaba caído, o si la Jetson se reinició
tras un apagón (el broker local restaura sus retenidos del disco), esas vitales
tienen minutos u horas. La única señal fiable es su `ts` (el OCR lo re-sella en
cada tick): una vital con `ts` fuera de ±FRESCURA_MAX_S NO es actual — ni se
pinta ni se evalúa para alertas. Falla CERRADO: sin `ts` o ilegible = no actual.

Timeout de datos (F1.2, decisión #1 de Dr. Milton): sobre la derivación de
arriba (que no cambia), `mostrado_vigente(cama, ahora)` añade "sin_datos" si
pasan más de DATOS_MAX_S sin una vital que CUENTE, o si nunca hubo una.
Prioridad: Sin conexión > Sin datos > estado de la cama. Cierra la limitación
del apagón (el `online` que el edge restaura de su disco ya no da verde) y
cubre el OCR colgado con proceso vivo y la desconexión silenciosa del teléfono.
Una vital CUENTA (se pinta, reinicia el timeout, se evalúa para alertas) solo
si es fresca, su edge no está en 0 y NO es una re-entrega:
  - retain=1 (el broker re-entrega el retenido al (re)suscribirse la app);
  - ts que no avanza sobre el último visto de esa cama (duplicado, o dos
    vitales selladas en el mismo segundo por el OCR);
  - la primera vital de la cama tras cada paso a 1 del enlace de su edge (el
    bridge re-publica los retenidos en CADA conexión, también la primera, con
    retain=0: indistinguible de una en vivo), o tras cambiar de edge.
Una re-entrega no pinta, no reinicia y no borra. Costo: 1-2 s de "Sin datos"
al abrir la app o tras reconectar. Si el NTP del edge da un paso atrás, sus
vitales no cuentan hasta superar el último ts visto: "Sin datos" transitorio
(falla cerrado). Una cama sin device_id no depende de ningún edge (F1.1): a
ella solo la protegen retain=1 y el ts que no avanza.

Módulo puro (sin flet): lo prueba pruebas/test_conexion.py.
"""

import time
from datetime import datetime, timezone

SIN_CONEXION = "sin_conexion"
SIN_DATOS = "sin_datos"

# Tolerancia de frescura: el OCR publica cada ~1 s con ts nuevo; 30 s cubre
# latencia y desfase de reloj (el edge tiene NTP y el teléfono, hora de red).
# Si el reloj del edge está MAL (p. ej. sin pila RTC tras un reinicio sin
# internet), las vitales se muestran "--": se falla cerrado, nunca abierto.
FRESCURA_MAX_S = 30

# Más de estos segundos sin una vital que cuente -> "Sin datos" (el OCR
# publica a ~1 Hz; la web usa 5 s).
DATOS_MAX_S = 10

# Clase de una vital recibida (clasificar_vital)
CUENTA = "cuenta"        # se pinta, reinicia el timeout y se evalúa
IGNORADA = "ignorada"    # re-entrega o edge en 0: ni pinta, ni reinicia, ni borra
VIEJA = "vieja"          # fuera de frescura o sin ts legible: "--"


def elegir_reloj(modulo_time=time):
    """Reloj del timeout de datos: (función, nombre).

    CLOCK_BOOTTIME (Linux/Android) es monotónico como time.monotonic — no
    salta si cambia la hora del sistema — pero SÍ cuenta el tiempo con el
    teléfono suspendido: al despertar, el timeout ve los minutos que pasaron.
    time.monotonic (CLOCK_MONOTONIC) no los cuenta: dejaría números viejos
    como actuales hasta 10 s. Fallback a monotonic donde no existe (Windows).
    """
    boottime = getattr(modulo_time, "CLOCK_BOOTTIME", None)
    if boottime is not None:
        try:
            modulo_time.clock_gettime(boottime)
            return (lambda: modulo_time.clock_gettime(boottime)), "CLOCK_BOOTTIME"
        except (AttributeError, OSError):
            pass
    return modulo_time.monotonic, "time.monotonic"


RELOJ, NOMBRE_RELOJ = elegir_reloj()


def _instante(ts):
    """ts del contrato (ISO-8601 con zona) -> datetime, o None si no sirve."""
    if not isinstance(ts, str):
        return None
    try:
        instante = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instante if instante.tzinfo is not None else None


def es_fresco(ts, ahora=None, maximo=FRESCURA_MAX_S):
    """¿La vital es ACTUAL? `ts` ISO-8601 UTC con sufijo Z (contrato)."""
    instante = _instante(ts)
    if instante is None:
        return False
    ahora = ahora or datetime.now(timezone.utc)
    return abs((ahora - instante).total_seconds()) <= maximo


class RegistroConexion:
    """Guarda enlaces por edge, estados por cama y la cama -> edge vigente.

    Cada `registrar_*` devuelve la lista de camas cuyo estado mostrado pudo
    cambiar, para que el dashboard refresque solo esas tarjetas.
    """

    def __init__(self):
        self._enlaces = {}         # device_id -> True | False | None
        self._device_de_cama = {}  # cama_id -> device_id (último visto)
        self._estados = {}         # cama_id -> "online" | "offline" | ...
        # timeout de datos (F1.2)
        self._ultima_cuenta = {}     # cama_id -> `ahora` (reloj monotónico) de la última vital que contó
        self._ultimo_ts = {}         # cama_id -> mayor ts (datetime) visto dentro de la frescura
        self._reconexiones = {}      # device_id -> cuántas veces pasó su enlace a 1
        self._reconexion_vista = {}  # cama_id -> (device_id, n) que ya consumió una vital suya

    def mostrado(self, cama_id):
        """"sin_conexion", el estado de la cama, o None si no se sabe nada."""
        device_id = self._device_de_cama.get(cama_id)
        if device_id is not None and self._enlaces.get(device_id) is False:
            return SIN_CONEXION
        return self._estados.get(cama_id)

    def registrar_estado(self, cama_id, estado):
        self._estados[cama_id] = estado
        return [cama_id]

    def registrar_vitales(self, cama_id, device_id):
        if device_id is None:
            return []
        anterior = self._device_de_cama.get(cama_id)
        self._device_de_cama[cama_id] = device_id
        if anterior is not None and anterior != device_id:
            # otro edge = otro reloj: el último ts visto del edge viejo no sirve
            # de referencia (su primera vital por el nuevo no cuenta de todos modos)
            self._ultimo_ts.pop(cama_id, None)
        return [cama_id] if anterior != device_id else []

    def registrar_enlace(self, device_id, conectado):
        """conectado: True (1), False (0) o None (desconocido).

        Un DESCONOCIDO no pisa un valor conocido: un retained borrado o un
        payload raro no pueden "desmarcar" un 0 vigente y ocultar la
        desconexión. Solo se guarda si no se sabía nada de ese edge.
        """
        if conectado is None and self._enlaces.get(device_id) is not None:
            return []
        if conectado is True and self._enlaces.get(device_id) is not True:
            # paso a 1 (desde 0, desconocido o nada): el bridge re-publica los
            # retenidos de ese edge en CADA conexión, también en la primera. Un
            # "1" repetido (1 -> 1) no es reconexión.
            self._reconexiones[device_id] = self._reconexiones.get(device_id, 0) + 1
        self._enlaces[device_id] = conectado
        return [cama for cama, d in self._device_de_cama.items() if d == device_id]

    # ---- timeout de datos (F1.2) ----

    def mostrado_vigente(self, cama_id, ahora):
        """Lo que la tarjeta MUESTRA: mostrado() + el timeout de datos.

        `ahora` = reloj monotónico (RELOJ). Sin conexión > Sin datos > estado.
        Sin ninguna vital que haya contado: "Sin datos" INMEDIATO (una tarjeta
        nacida solo con vitales viejas nunca llega a verde).
        """
        base = self.mostrado(cama_id)
        if base == SIN_CONEXION:
            return SIN_CONEXION
        ultima = self._ultima_cuenta.get(cama_id)
        if ultima is None or ahora - ultima > DATOS_MAX_S:
            return SIN_DATOS
        return base

    def clasificar_vital(self, cama_id, ts, retenido, ahora, ahora_utc=None):
        """CUENTA, IGNORADA o VIEJA; si CUENTA, reinicia el timeout de la cama.

        Llamar DESPUÉS de registrar_vitales (usa el edge vigente de la cama).
        `ahora` = reloj monotónico; `ahora_utc` = hora de pared para la
        frescura (inyectable en tests).
        """
        tras_reconexion = self._consumir_reconexion(cama_id)
        if not es_fresco(ts, ahora_utc):
            return VIEJA
        instante = _instante(ts)
        anterior = self._ultimo_ts.get(cama_id)
        if anterior is None or instante > anterior:
            self._ultimo_ts[cama_id] = instante
        if retenido or tras_reconexion or (anterior is not None and instante <= anterior):
            return IGNORADA
        if self.mostrado(cama_id) == SIN_CONEXION:
            return IGNORADA
        self._ultima_cuenta[cama_id] = ahora
        return CUENTA

    def _consumir_reconexion(self, cama_id):
        """¿Es la primera vital de la cama desde la última conexión de su edge?

        Se compara (edge, n) y no solo n: si la cama cambió de edge, su primera
        vital por el nuevo tampoco cuenta, aunque los contadores coincidan. Una
        cama que el teléfono aún no conocía, de un edge que ya se conectó,
        también cae aquí: su primera vital no cuenta (falla cerrado, ~1 s).
        """
        device_id = self._device_de_cama.get(cama_id)
        actual = (device_id, self._reconexiones.get(device_id, 0) if device_id is not None else 0)
        vista = self._reconexion_vista.get(cama_id, (device_id, 0))
        self._reconexion_vista[cama_id] = actual
        return vista != actual
