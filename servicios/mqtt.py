"""Cliente MQTT de la app: vitales, estado de cama y enlace de cada edge.

Blindaje (lección de los callbacks de paho en el backend, ADR-021/022): en
paho 2.x una excepción dentro de un callback MATA el hilo de red sin
reconexión — la app se quedaba en "Conectado" con las vitales congeladas.
Cowork lo reprodujo con el retained `monitoreo/edge/jetson-01/bridge = 1`
(ADR-024): json.loads devolvía int y `"signos" in 1` lanzaba TypeError. Por eso:
  - suscripción EXPLÍCITA a los tres topics que la app entiende — nunca
    `monitoreo/#` (por ahí también pasarán los lotes de backfill del backend);
  - despacho POR TOPIC antes de parsear, no adivinando por claves del JSON;
  - TODO el cuerpo de cada callback bajo except con log.
"""

import json

import paho.mqtt.client as mqtt

BROKER = "100.110.157.112"
PUERTO = 1883

# QoS 0: el live es estado retenido; con sesión limpia, QoS 1 no aporta al
# reconectar. Orden deliberado: paho manda la lista en UN solo SUBSCRIBE y
# mosquitto entrega los retenidos filtro por filtro en ese orden, así que el
# enlace (edge=0) llega antes que las vitales retenidas y la tarjeta nace
# "Sin conexión". Eso es comportamiento de mosquitto, no garantía de MQTT: la
# defensa que NO depende del orden es la frescura del `ts` en el dashboard
# (datos/conexion.py): una vital retenida vieja nunca se pinta ni dispara
# alertas, llegue cuando llegue.
SUSCRIPCIONES = [
    ("monitoreo/edge/+/bridge", 0),
    ("monitoreo/estado/+", 0),
    ("monitoreo/vitales/+", 0),
]


def _objeto_json(payload):
    datos = json.loads(payload.decode("utf-8"))
    if not isinstance(datos, dict):
        raise ValueError(f"se esperaba un objeto JSON, llegó {type(datos).__name__}")
    return datos


def _texto_o_none(valor):
    return valor if isinstance(valor, str) and valor else None


def despachar(topic, payload, al_vitales, al_estado_cama, al_enlace_edge):
    """Enruta un mensaje por su TOPIC y llama al callback que corresponde.

    Lanza ante un payload inválido: quien llama (_al_mensaje) lo atrapa y lo
    registra, sin matar el hilo de paho.
    """
    partes = topic.split("/")

    if len(partes) == 4 and partes[0] == "monitoreo" and partes[1] == "edge" and partes[3] == "bridge":
        # Enlace del edge: payload "1"/"0" (no JSON). Vacío (retained borrado)
        # o cualquier otra cosa = DESCONOCIDO: no se marca nada.
        device_id = partes[2]
        crudo = payload.decode("utf-8", errors="replace").strip()
        if crudo == "1":
            conectado = True
        elif crudo == "0":
            conectado = False
        else:
            print(f"[mqtt] enlace de {device_id} con payload desconocido {crudo[:20]!r}: se trata como desconocido")
            conectado = None
        if al_enlace_edge is not None:
            al_enlace_edge(device_id, conectado)

    elif len(partes) == 3 and partes[0] == "monitoreo" and partes[1] == "vitales":
        datos = _objeto_json(payload)
        signos = datos.get("signos")
        if not isinstance(signos, dict):
            raise ValueError("vitales sin 'signos' válido")
        cama_id = _texto_o_none(datos.get("cama_id")) or partes[2]
        # device_id es opcional: sin él las vitales se muestran igual. El ts
        # viaja crudo: el dashboard decide si la vital es actual.
        al_vitales(cama_id, signos, _texto_o_none(datos.get("device_id")),
                   datos.get("ts"))

    elif len(partes) == 3 and partes[0] == "monitoreo" and partes[1] == "estado":
        datos = _objeto_json(payload)
        estado = _texto_o_none(datos.get("estado"))
        if estado is None:
            raise ValueError("estado sin campo 'estado' válido")
        cama_id = _texto_o_none(datos.get("cama_id")) or partes[2]
        al_estado_cama(cama_id, estado)

    else:
        print(f"[mqtt] topic ignorado: {topic}")


class ClienteMQTT:
    def __init__(self, al_vitales, al_estado, al_estado_cama, al_enlace_edge=None):
        self.al_vitales = al_vitales
        self.al_estado = al_estado
        self.al_estado_cama = al_estado_cama
        self.al_enlace_edge = al_enlace_edge

    # Los callbacks son métodos (no closures) para poder probarlos sin red.
    # Firma VERSION2 de paho: 5 argumentos posicionales.

    def _al_conectar(self, client, userdata, flags, reason_code, properties=None):
        try:
            if getattr(reason_code, "is_failure", False):
                # paho también invoca on_connect cuando el broker RECHAZA
                print(f"conexión rechazada por el broker: {reason_code}")
                self.al_estado(False)
                return
            client.subscribe(SUSCRIPCIONES)
            self.al_estado(True)
            print("conectado al broker")
        except Exception as e:
            # hasta el print del except va protegido: si stdout falla (p. ej.
            # almacenamiento lleno en Android), la excepción no debe escapar
            try:
                print(f"error en on_connect: {e}")
            except Exception:
                pass

    def _al_desconectar(self, client, userdata, flags, reason_code, properties=None):
        try:
            self.al_estado(False)
            print("broker no conectado")
        except Exception as e:
            try:
                print(f"error en on_disconnect: {e}")
            except Exception:
                pass

    def _al_mensaje(self, client, userdata, msg):
        try:
            despachar(msg.topic, msg.payload, self.al_vitales,
                      self.al_estado_cama, self.al_enlace_edge)
        except Exception as e:
            try:
                print(f"[mqtt] mensaje descartado en {msg.topic}: {e}")
            except Exception:
                pass

    def iniciar(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = self._al_conectar
        client.on_message = self._al_mensaje
        client.on_disconnect = self._al_desconectar
        client.connect_async(BROKER, PUERTO, keepalive=15)
        client.loop_start()
