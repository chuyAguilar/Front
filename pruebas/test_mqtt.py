"""Blindaje del cliente MQTT: nada que llegue del broker puede matar el hilo.

Regresión directa del bug que reprodujo Cowork (F1.1): el retained
`monitoreo/edge/jetson-01/bridge = 1` hacía que json.loads devolviera int y
`"signos" in 1` lanzara TypeError dentro del callback — en paho 2.x eso mata
el hilo de red y la app queda "Conectado" con las vitales congeladas.
"""

import json

from servicios import mqtt as modulo
from servicios.mqtt import SUSCRIPCIONES, ClienteMQTT, despachar


class Msg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class Registro:
    def __init__(self):
        self.vitales = []
        self.estados = []
        self.enlaces = []
        self.conexion = []

    def al_vitales(self, cama_id, signos, device_id, ts):
        self.vitales.append((cama_id, signos, device_id, ts))

    def al_estado_cama(self, cama_id, estado):
        self.estados.append((cama_id, estado))

    def al_enlace_edge(self, device_id, conectado):
        self.enlaces.append((device_id, conectado))

    def al_estado(self, conectado):
        self.conexion.append(conectado)


def _cliente(r):
    return ClienteMQTT(r.al_vitales, r.al_estado, r.al_estado_cama, r.al_enlace_edge)


VITALES = {
    "contrato": "1.1", "cama_id": "cama-09", "device_id": "jetson-01",
    "ts": "2026-09-22T10:00:00Z", "origen": "ocr",
    "signos": {"fc": {"valor": 142}, "pni": None},
}


def _json(d):
    return json.dumps(d).encode()


def test_retained_del_bridge_ya_no_mata_el_callback():
    # EL bug: payload b"1" en el topic del edge.
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg("monitoreo/edge/jetson-01/bridge", b"1"))
    assert r.enlaces == [("jetson-01", True)]
    assert r.vitales == []


def test_enlace_cero_y_desconocidos():
    r = Registro()
    c = _cliente(r)
    c._al_mensaje(None, None, Msg("monitoreo/edge/jetson-01/bridge", b"0"))
    # vacío (retained borrado) o cualquier otra cosa = DESCONOCIDO (None)
    for raro in (b"", b"true", b"2", b"\xff\xfe"):
        c._al_mensaje(None, None, Msg("monitoreo/edge/jetson-02/bridge", raro))
    assert r.enlaces[0] == ("jetson-01", False)
    assert r.enlaces[1:] == [("jetson-02", None)] * 4


def test_vitales_con_device_id_y_ts():
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", _json(VITALES)))
    assert r.vitales == [("cama-09", VITALES["signos"], "jetson-01", "2026-09-22T10:00:00Z")]


def test_vitales_sin_device_id_se_muestran_igual():
    # añadido C: device_id opcional — nunca debe caer al except y perderse
    sin_device = {k: v for k, v in VITALES.items() if k != "device_id"}
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", _json(sin_device)))
    assert r.vitales == [("cama-09", VITALES["signos"], None, "2026-09-22T10:00:00Z")]


def test_vitales_sin_ts_llegan_igual_y_el_dashboard_decide():
    # el ts viaja crudo (None si falta): la frescura la juzga el dashboard,
    # que falla cerrado; el despacho no descarta el mensaje
    sin_ts = {k: v for k, v in VITALES.items() if k != "ts"}
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", _json(sin_ts)))
    assert r.vitales == [("cama-09", VITALES["signos"], "jetson-01", None)]


def test_device_id_no_texto_se_trata_como_ausente():
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09",
                                            _json({**VITALES, "device_id": 5})))
    assert r.vitales[0][2] is None


def test_estado_de_cama():
    r = Registro()
    _cliente(r)._al_mensaje(None, None, Msg(
        "monitoreo/estado/cama-09",
        _json({"cama_id": "cama-09", "device_id": "jetson-01", "estado": "offline"})))
    assert r.estados == [("cama-09", "offline")]


def test_basura_se_descarta_sin_propagar(capsys):
    r = Registro()
    c = _cliente(r)
    for topic, payload in (
        ("monitoreo/vitales/cama-09", b"no es json"),
        ("monitoreo/vitales/cama-09", b"1"),              # JSON pero no objeto
        ("monitoreo/vitales/cama-09", _json({"cama_id": "cama-09"})),  # sin signos
        ("monitoreo/estado/cama-09", b"[]"),
        ("monitoreo/estado/cama-09", _json({"cama_id": "cama-09"})),   # sin estado
        ("monitoreo/vitales/cama-09", b""),               # retained borrado
    ):
        c._al_mensaje(None, None, Msg(topic, payload))   # no debe lanzar
    assert r.vitales == [] and r.estados == []
    assert "mensaje descartado" in capsys.readouterr().out


def test_excepcion_del_dashboard_tampoco_escapa(capsys):
    # el blindaje cubre también los errores aguas abajo (dashboard/tarjetas)
    def revienta(*_a):
        raise KeyError("boom")

    c = ClienteMQTT(revienta, lambda _c: None, revienta, revienta)
    c._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", _json(VITALES)))
    c._al_mensaje(None, None, Msg("monitoreo/edge/jetson-01/bridge", b"0"))
    assert capsys.readouterr().out.count("mensaje descartado") == 2


def test_topic_ajeno_se_ignora():
    r = Registro()
    c = _cliente(r)
    c._al_mensaje(None, None, Msg("monitoreo/backfill/jetson-01", b"x" * 1000))
    c._al_mensaje(None, None, Msg("$SYS/broker/connection/x/state", b"1"))
    assert (r.vitales, r.estados, r.enlaces) == ([], [], [])


def test_suscripciones_explicitas_nunca_el_comodin():
    topics = [t for t, _qos in SUSCRIPCIONES]
    assert topics == ["monitoreo/edge/+/bridge", "monitoreo/estado/+", "monitoreo/vitales/+"]
    assert "monitoreo/#" not in topics
    assert all(qos == 0 for _t, qos in SUSCRIPCIONES)


class ClientePaho:
    def __init__(self):
        self.suscrito = None

    def subscribe(self, topics):
        self.suscrito = topics


class Codigo:
    def __init__(self, fallo):
        self.is_failure = fallo

    def __str__(self):
        return "Not authorized" if self.is_failure else "Success"


def test_al_conectar_suscribe_con_la_aridad_real_de_paho_v2():
    r = Registro()
    paho = ClientePaho()
    _cliente(r)._al_conectar(paho, None, None, Codigo(False), None)  # 5 args
    assert paho.suscrito == SUSCRIPCIONES
    assert r.conexion == [True]


def test_connack_rechazado_no_suscribe_ni_dice_conectado():
    r = Registro()
    paho = ClientePaho()
    _cliente(r)._al_conectar(paho, None, None, Codigo(True), None)
    assert paho.suscrito is None
    assert r.conexion == [False]


def test_ni_el_print_del_except_escapa_de_los_callbacks(monkeypatch):
    # si stdout falla (p. ej. almacenamiento lleno en Android) el print del
    # except también lanza: tampoco eso puede escapar y matar el hilo de paho
    def revienta(*_a, **_k):
        raise OSError("stdout roto")

    monkeypatch.setattr(modulo, "print", revienta, raising=False)
    c = ClienteMQTT(revienta, revienta, revienta, revienta)
    c._al_conectar(ClientePaho(), None, None, Codigo(False), None)
    c._al_conectar(ClientePaho(), None, None, Codigo(True), None)
    c._al_desconectar(None, None, None, Codigo(False), None)
    c._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", _json(VITALES)))
    c._al_mensaje(None, None, Msg("monitoreo/vitales/cama-09", b"basura"))
    c._al_mensaje(None, None, Msg("otro/topic", b"x"))


def test_despachar_es_la_misma_ruta_que_usa_el_callback():
    # despachar lanza ante basura (quien la atrapa es _al_mensaje)
    import pytest

    r = Registro()
    with pytest.raises(ValueError):
        despachar("monitoreo/vitales/cama-09", b"1",
                  r.al_vitales, r.al_estado_cama, r.al_enlace_edge)
    assert modulo.BROKER == "100.110.157.112"
