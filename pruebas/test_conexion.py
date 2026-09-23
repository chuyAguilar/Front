"""Estado mostrado DERIVADO (datos/conexion.py) — añadidos A, B, C, D de Cowork."""

from datetime import datetime, timezone

from datos.conexion import FRESCURA_MAX_S, SIN_CONEXION, RegistroConexion, es_fresco

AHORA = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def test_frescura_ts_del_contrato():
    assert es_fresco("2026-09-22T10:00:00Z", AHORA)
    assert es_fresco("2026-09-22T09:59:31Z", AHORA)          # 29 s
    assert es_fresco("2026-09-22T10:00:29Z", AHORA)          # reloj del edge adelantado
    assert FRESCURA_MAX_S == 30
    assert es_fresco("2026-09-22T09:59:30Z", AHORA)          # justo en el borde


def test_frescura_falla_cerrado():
    assert not es_fresco("2026-09-22T09:59:29Z", AHORA)      # 31 s: vieja
    assert not es_fresco("2026-09-22T08:00:00Z", AHORA)      # restaurada tras apagón
    assert not es_fresco("2026-09-22T10:05:00Z", AHORA)      # del futuro (reloj mal)
    for malo in (None, "", "ayer", 1758535200, "2026-09-22T10:00:00"):  # sin zona
        assert not es_fresco(malo, AHORA)


def test_frescura_sin_ahora_usa_el_reloj():
    assert es_fresco(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def test_d_edge_cero_manda_sobre_el_estado_de_la_cama():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "online")      # el retained "online" miente
    r.registrar_enlace("jetson-01", False)
    assert r.mostrado("cama-09") == SIN_CONEXION


def test_d_edge_uno_no_fuerza_online():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "offline")
    r.registrar_enlace("jetson-01", True)
    assert r.mostrado("cama-09") == "offline"    # el estado de la cama manda


def test_d_derivado_no_ultimo_evento_gana():
    # 0 -> estado online llega DESPUÉS -> sigue "sin conexión"
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_enlace("jetson-01", False)
    r.registrar_estado("cama-09", "online")
    assert r.mostrado("cama-09") == SIN_CONEXION
    # vuelve el enlace -> se muestra el estado de la cama
    r.registrar_enlace("jetson-01", True)
    assert r.mostrado("cama-09") == "online"


def test_d_enlace_desconocido_no_marca():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "online")
    r.registrar_enlace("jetson-01", None)
    assert r.mostrado("cama-09") == "online"
    # sin retained del edge (nunca llegó nada) tampoco marca
    r2 = RegistroConexion()
    r2.registrar_vitales("cama-09", "jetson-01")
    assert r2.mostrado("cama-09") is None


def test_d_desconocido_no_desmarca_un_cero_vigente():
    # un retained borrado o un payload raro NO pueden ocultar la desconexión
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "online")
    r.registrar_enlace("jetson-01", False)
    assert r.registrar_enlace("jetson-01", None) == []
    assert r.mostrado("cama-09") == SIN_CONEXION
    # solo un 1 explícito lo levanta
    r.registrar_enlace("jetson-01", True)
    assert r.mostrado("cama-09") == "online"


def test_a_enlace_antes_que_las_vitales():
    # el retained 0 del edge llega ANTES que cualquier vital: se guarda por
    # device_id y se aplica en cuanto la cama se asocia a ese edge
    r = RegistroConexion()
    assert r.registrar_enlace("jetson-01", False) == []   # aún sin camas
    r.registrar_vitales("cama-09", "jetson-01")
    assert r.mostrado("cama-09") == SIN_CONEXION


def test_b_cama_que_cambia_de_jetson_no_queda_colgada():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_estado("cama-09", "online")
    assert r.registrar_vitales("cama-09", "jetson-02") == ["cama-09"]  # cambio
    r.registrar_enlace("jetson-01", False)          # cae el edge VIEJO
    assert r.mostrado("cama-09") == "online"
    assert r.registrar_enlace("jetson-01", False) == []   # ya no le pertenece
    r.registrar_enlace("jetson-02", False)          # cae el edge actual
    assert r.mostrado("cama-09") == SIN_CONEXION


def test_c_vitales_sin_device_id_no_tocan_el_mapeo():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    assert r.registrar_vitales("cama-09", None) == []
    r.registrar_enlace("jetson-01", False)
    assert r.mostrado("cama-09") == SIN_CONEXION    # sigue asociada
    # una cama que nunca trajo device_id no depende de ningún edge
    r.registrar_estado("cama-10", "online")
    r.registrar_vitales("cama-10", None)
    assert r.mostrado("cama-10") == "online"


def test_enlace_afecta_solo_a_las_camas_de_ese_edge():
    r = RegistroConexion()
    r.registrar_vitales("cama-09", "jetson-01")
    r.registrar_vitales("cama-10", "jetson-01")
    r.registrar_vitales("cama-11", "jetson-02")
    assert sorted(r.registrar_enlace("jetson-01", False)) == ["cama-09", "cama-10"]
    assert r.mostrado("cama-11") is None
