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

Módulo puro (sin flet): lo prueba pruebas/test_conexion.py.
"""

from datetime import datetime, timezone

SIN_CONEXION = "sin_conexion"

# Tolerancia de frescura: el OCR publica cada ~1 s con ts nuevo; 30 s cubre
# latencia y desfase de reloj (el edge tiene NTP y el teléfono, hora de red).
# Si el reloj del edge está MAL (p. ej. sin pila RTC tras un reinicio sin
# internet), las vitales se muestran "--": se falla cerrado, nunca abierto.
FRESCURA_MAX_S = 30


def es_fresco(ts, ahora=None, maximo=FRESCURA_MAX_S):
    """¿La vital es ACTUAL? `ts` ISO-8601 UTC con sufijo Z (contrato)."""
    if not isinstance(ts, str):
        return False
    try:
        instante = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if instante.tzinfo is None:
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
        return [cama_id] if anterior != device_id else []

    def registrar_enlace(self, device_id, conectado):
        """conectado: True (1), False (0) o None (desconocido).

        Un DESCONOCIDO no pisa un valor conocido: un retained borrado o un
        payload raro no pueden "desmarcar" un 0 vigente y ocultar la
        desconexión. Solo se guarda si no se sabía nada de ese edge.
        """
        if conectado is None and self._enlaces.get(device_id) is not None:
            return []
        self._enlaces[device_id] = conectado
        return [cama for cama, d in self._device_de_cama.items() if d == device_id]
