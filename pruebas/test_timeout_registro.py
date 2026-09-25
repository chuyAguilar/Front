"""Timeout de datos (F1.2) en la lógica pura de datos/conexion.py.

"ahora" (reloj monotónico) y la hora de pared de la frescura se inyectan:
nada depende del reloj real. Los tests de F1.1 (test_conexion.py) no cambian.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from datos import conexion
from datos.conexion import (CUENTA, DATOS_MAX_S, IGNORADA, SIN_CONEXION, SIN_DATOS, VIEJA,
                            RegistroConexion, elegir_reloj)

UTC0 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)


def _ts(s):
    """ts del contrato (resolución de 1 s, como el OCR) a UTC0 + s."""
    return (UTC0 + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _vital(r, s, ahora, retenido=False, cama="cama-09", device="jetson-01", edad_s=0):
    """Llega una vital sellada en UTC0+s; la pared marca UTC0+s+edad_s."""
    r.registrar_vitales(cama, device)
    return r.clasificar_vital(cama, _ts(s), retenido, ahora,
                              UTC0 + timedelta(seconds=s + edad_s))


def _cama_online(r, cama="cama-09", device="jetson-01"):
    """Así abre la app: le llegan (en el orden de SUSCRIPCIONES) el enlace "1"
    retenido, el estado retenido y la última vital retenida (retain=1, que no
    cuenta y consume la marca de la conexión del edge)."""
    r.registrar_vitales(cama, device)
    r.registrar_enlace(device, True)
    r.registrar_estado(cama, "online")
    assert _vital(r, -1, ahora=0.0, retenido=True, cama=cama, device=device) == IGNORADA


def test_constantes():
    assert DATOS_MAX_S == 10
    assert SIN_DATOS == "sin_datos"


def test_nunca_hubo_vital_que_cuente_es_sin_datos_inmediato():
    r = RegistroConexion()
    _cama_online(r)
    assert r.mostrado("cama-09") == "online"          # la derivación F1.1 no cambia
    assert r.mostrado_vigente("cama-09", 0.0) == SIN_DATOS


def test_timeout_a_los_10_s():
    r = RegistroConexion()
    _cama_online(r)
    assert _vital(r, 0, ahora=100.0) == CUENTA
    assert r.mostrado_vigente("cama-09", 100.0) == "online"
    assert r.mostrado_vigente("cama-09", 110.0) == "online"     # borde: 10 s justos
    assert r.mostrado_vigente("cama-09", 110.01) == SIN_DATOS   # más de 10 s


def test_la_vital_que_cuenta_reinicia_el_timeout_y_levanta_sin_datos():
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    assert r.mostrado_vigente("cama-09", 115.0) == SIN_DATOS
    assert _vital(r, 15, ahora=115.0) == CUENTA
    assert r.mostrado_vigente("cama-09", 115.0) == "online"     # la levanta
    assert r.mostrado_vigente("cama-09", 125.0) == "online"
    assert r.mostrado_vigente("cama-09", 125.5) == SIN_DATOS


def test_prioridad_sin_conexion_sin_datos_estado():
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    r.registrar_enlace("jetson-01", False)
    assert r.mostrado_vigente("cama-09", 100.0) == SIN_CONEXION  # aun con datos frescos
    assert r.mostrado_vigente("cama-09", 500.0) == SIN_CONEXION  # y con timeout
    r.registrar_enlace("jetson-01", True)
    assert r.mostrado_vigente("cama-09", 500.0) == SIN_DATOS     # Sin datos > estado
    r2 = RegistroConexion()
    r2.registrar_vitales("cama-09", "jetson-01")
    r2.registrar_estado("cama-09", "offline")
    _vital(r2, 0, ahora=100.0)
    assert r2.mostrado_vigente("cama-09", 101.0) == "offline"    # el estado, si hay datos
    r3 = RegistroConexion()
    _vital(r3, 0, ahora=100.0)
    assert r3.mostrado_vigente("cama-09", 101.0) is None         # estado aún desconocido


def test_con_el_enlace_en_0_la_vital_no_cuenta():
    r = RegistroConexion()
    _cama_online(r)
    r.registrar_enlace("jetson-01", False)
    assert _vital(r, 0, ahora=100.0) == IGNORADA
    assert r.mostrado_vigente("cama-09", 100.0) == SIN_CONEXION


def test_retain_1_no_cuenta_y_la_primera_en_vivo_si():
    # al (re)suscribirse la app, el broker re-entrega la retenida con retain=1
    r = RegistroConexion()
    _cama_online(r)
    assert _vital(r, 0, ahora=100.0, retenido=True) == IGNORADA
    assert r.mostrado_vigente("cama-09", 100.0) == SIN_DATOS
    assert _vital(r, 1, ahora=101.0) == CUENTA
    assert r.mostrado_vigente("cama-09", 101.0) == "online"


def test_retain_1_con_ts_ya_visto_no_reinicia_el_timeout():
    # el OCR se cuelga; el teléfono se reconecta a los 15 s y le re-entregan
    # la ÚLTIMA vital (retain=1, ts de hace 15 s: dentro de la frescura)
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    assert r.mostrado_vigente("cama-09", 111.0) == SIN_DATOS
    assert _vital(r, 0, ahora=115.0, retenido=True, edad_s=15) == IGNORADA
    assert r.mostrado_vigente("cama-09", 115.0) == SIN_DATOS    # nada de volver a verde


def test_mismo_ts_no_cuenta_y_no_parpadea():
    # el OCR sella al segundo: dos vitales con el MISMO ts -> la segunda no
    # cuenta, y tampoco provoca "Sin datos" (la primera ya reinició)
    r = RegistroConexion()
    _cama_online(r)
    assert _vital(r, 0, ahora=100.0) == CUENTA
    assert _vital(r, 0, ahora=100.5) == IGNORADA
    assert r.mostrado_vigente("cama-09", 100.5) == "online"
    assert r.mostrado_vigente("cama-09", 110.0) == "online"     # el timeout corre desde la 1ª
    assert _vital(r, 1, ahora=101.0) == CUENTA


def test_ts_que_retrocede_no_cuenta_hasta_superar_el_ultimo_visto():
    # paso atrás del NTP del edge: "Sin datos" transitorio (falla cerrado)
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 10, ahora=100.0)
    assert _vital(r, 5, ahora=101.0) == IGNORADA
    assert _vital(r, 10, ahora=102.0) == IGNORADA
    assert _vital(r, 11, ahora=103.0) == CUENTA


def test_la_primera_vital_tras_0_a_1_no_cuenta():
    # el bridge re-publica al volver el enlace con retain=0: aunque su ts sea
    # nuevo para el teléfono (sellada durante el corte), no cuenta
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    r.registrar_enlace("jetson-01", False)
    r.registrar_enlace("jetson-01", True)
    assert _vital(r, 20, ahora=130.0) == IGNORADA
    assert r.mostrado_vigente("cama-09", 130.0) == SIN_DATOS
    assert _vital(r, 21, ahora=131.0) == CUENTA
    assert r.mostrado_vigente("cama-09", 131.0) == "online"


def test_si_la_primera_tras_0_a_1_es_vieja_tambien_consume_la_reconexion():
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    r.registrar_enlace("jetson-01", False)
    r.registrar_enlace("jetson-01", True)
    assert _vital(r, 1, ahora=200.0, edad_s=100) == VIEJA       # el retenido del OCR caído
    assert _vital(r, 101, ahora=201.0) == CUENTA                # la siguiente, en vivo


def test_cualquier_paso_a_1_es_reconexion_pero_un_1_repetido_no():
    # desconocido -> 1 también: el bridge re-publica en CADA conexión. Un "1"
    # repetido (el bridge lo publica dos veces al conectar) no suma otra.
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "online")
    r.registrar_enlace("jetson-01", None)
    r.registrar_enlace("jetson-01", True)
    r.registrar_enlace("jetson-01", True)
    assert _vital(r, 0, ahora=100.0) == IGNORADA      # la re-publicación
    assert _vital(r, 1, ahora=101.0) == CUENTA
    r.registrar_enlace("jetson-01", True)              # otro "1" repetido
    assert _vital(r, 2, ahora=102.0) == CUENTA


def test_primera_conexion_del_edge_con_la_app_abierta():
    # día de instalación: el enlace no existía y el bridge conecta por primera
    # vez; re-publica la última vital del broker local (sellada hace 25 s)
    r = RegistroConexion()
    r.registrar_vitales("cama-02", "jetson-03")
    r.registrar_estado("cama-02", "online")
    r.registrar_enlace("jetson-03", True)
    assert _vital(r, 0, ahora=100.0, cama="cama-02", device="jetson-03", edad_s=25) == IGNORADA
    assert r.mostrado_vigente("cama-02", 100.0) == SIN_DATOS


def test_la_cama_que_cambia_de_edge_no_cuenta_su_primera_vital_por_el_nuevo():
    # aunque el contador de conexiones de los dos edges coincida
    r = RegistroConexion()
    _cama_online(r)                                    # jetson-01: 1 conexión, consumida
    assert _vital(r, 0, ahora=100.0) == CUENTA
    r.registrar_enlace("jetson-02", True)              # jetson-02: también 1 conexión
    assert _vital(r, 20, ahora=120.0, device="jetson-02") == IGNORADA
    assert _vital(r, 21, ahora=121.0, device="jetson-02") == CUENTA


def test_cambiar_de_edge_olvida_el_ultimo_ts_del_viejo():
    # el reloj del edge viejo iba adelantado: el ts del nuevo no debe quedar
    # "sin avanzar" frente a un reloj que ya no es el suyo
    r = RegistroConexion()
    _cama_online(r)
    assert _vital(r, 100, ahora=100.0) == CUENTA
    assert _vital(r, 80, ahora=101.0, device="jetson-02", edad_s=21) == IGNORADA   # 1ª por el nuevo
    assert _vital(r, 81, ahora=102.0, device="jetson-02", edad_s=21) == CUENTA


def test_cama_nueva_de_un_edge_que_ya_reconecto():
    # el teléfono nunca vio esa cama: su primera vital puede ser la
    # re-publicación del bridge -> no cuenta (falla cerrado, ~1 s)
    r = RegistroConexion()
    r.registrar_enlace("jetson-01", False)
    r.registrar_enlace("jetson-01", True)
    assert _vital(r, 0, ahora=100.0, cama="cama-10") == IGNORADA
    assert _vital(r, 1, ahora=101.0, cama="cama-10") == CUENTA


def test_vital_vieja_o_sin_ts_no_reinicia_el_timeout():
    r = RegistroConexion()
    _cama_online(r)
    _vital(r, 0, ahora=100.0)
    assert _vital(r, 5, ahora=108.0, edad_s=45) == VIEJA
    r.registrar_vitales("cama-09", "jetson-01")
    assert r.clasificar_vital("cama-09", None, False, 109.0) == VIEJA
    assert r.mostrado_vigente("cama-09", 110.5) == SIN_DATOS


# ---- reloj del timeout ----

def test_reloj_sin_boottime_cae_a_monotonic():
    falso = SimpleNamespace(monotonic=lambda: 7.0)
    funcion, nombre = elegir_reloj(falso)
    assert nombre == "time.monotonic"
    assert funcion() == 7.0


def test_reloj_con_boottime_lo_usa():
    falso = SimpleNamespace(CLOCK_BOOTTIME=7, clock_gettime=lambda _c: 42.0,
                            monotonic=lambda: 1.0)
    funcion, nombre = elegir_reloj(falso)
    assert nombre == "CLOCK_BOOTTIME"
    assert funcion() == 42.0


def test_reloj_con_boottime_que_falla_cae_a_monotonic():
    def falla(_c):
        raise OSError("no soportado")

    falso = SimpleNamespace(CLOCK_BOOTTIME=7, clock_gettime=falla, monotonic=lambda: 1.0)
    assert elegir_reloj(falso)[1] == "time.monotonic"


@pytest.mark.skipif(sys.platform != "win32", reason="el fallback real solo aplica en Windows")
def test_en_windows_el_reloj_real_es_monotonic():
    assert conexion.NOMBRE_RELOJ == "time.monotonic"
    assert conexion.RELOJ is time.monotonic


@pytest.mark.skipif(not hasattr(time, "CLOCK_BOOTTIME"), reason="sin CLOCK_BOOTTIME (no Linux/Android)")
def test_en_linux_el_reloj_real_es_boottime():
    assert conexion.NOMBRE_RELOJ == "CLOCK_BOOTTIME"
